"""Build the dashboard document and publish it to the store (and optionally a file).

The dashboard reads the newest published_result row through a read-only role,
so a data refresh never needs a redeploy or a commit.
"""
import json
import time
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import Engine

from weather_vs_market.analysis import live
from weather_vs_market.analysis import verification as V
from weather_vs_market.config import ROOT, Settings
from weather_vs_market.pipeline.ingest import ENSEMBLE_MODEL
from weather_vs_market.storage import store

SCHEMA_VERSION = 2
BACKTEST_RESULTS = ROOT / "results" / "backtest_test.json"


def lead_points(settings: Settings) -> list[V.LeadPoint]:
    return [V.LeadPoint(lp.name, lp.day_offset, lp.hour) for lp in settings.evaluation.lead_points]


def live_scores(settings: Settings, engine: Engine) -> dict:
    """Forward scores of the live ensemble model against live quotes, per venue."""
    out = {}
    for venue in ("kalshi", "polymarket"):
        events = V.event_frame(engine, venue=venue, model=ENSEMBLE_MODEL,
                               lead_points=lead_points(settings),
                               tz_for_city=settings.city_timezones(venue), quote_sources=("live",),
                               tolerance_s=settings.evaluation.tolerance_hours * 3600,
                               quoted_events_only=True)
        order = [lp.name for lp in lead_points(settings)]
        out[venue] = {"summary": V.summarize(events, order=order) if events else [],
                      "n_events": len(events)}
    return out


LIVE_SCORES_MAX_AGE_S = 6 * 3600


def cached_live_scores(settings: Settings, engine: Engine, now: float) -> dict:
    """Live scores change only as days settle, but recomputing them reads every live
    quote and prediction; on Neon's free tier (5 GB egress a month) doing that on
    every hourly publish was most of the budget. Recompute at most every 6 hours."""
    cached = store.load_result(engine, "live_scores")
    if cached and now - cached["generated_ts"] < LIVE_SCORES_MAX_AGE_S:
        return cached["scores"]
    scores = live_scores(settings, engine)
    store.save_result(engine, "live_scores", {"generated_ts": now, "scores": scores}, generated_ts=now)
    return scores


def build_doc(settings: Settings, engine: Engine, now: float | None = None) -> dict:
    backtest = json.loads(BACKTEST_RESULTS.read_text()) if BACKTEST_RESULTS.exists() else None
    generated = now if now is not None else time.time()
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_ts": generated,
        "backtest": backtest,
        # The frozen model scored on every target date since the freeze; refreshed weekly.
        "forward": store.load_result(engine, "forward"),
        # blend_v1 (protocol v2): market and model pooled, scored against the market.
        "blend": {"test": store.load_result(engine, "blend_test"),
                  "forward": store.load_result(engine, "blend_forward")},
        "live": {"model": ENSEMBLE_MODEL, "scores": cached_live_scores(settings, engine, generated)},
        "tracking": live.tracking_summary(engine),
        "live_disagreements": live.current_disagreements(engine, model=ENSEMBLE_MODEL, now=now),
    }


def publish(settings: Settings, engine: Engine, out_file: str | None = None) -> dict:
    doc = build_doc(settings, engine)
    store.publish(engine, doc, generated_ts=doc["generated_ts"])
    if out_file:
        Path(out_file).parent.mkdir(parents=True, exist_ok=True)
        Path(out_file).write_text(json.dumps(doc))
    return doc


def dump_tables(engine: Engine, out_dir: str) -> dict[str, int]:
    """Write every table to Parquet so anyone can rerun the analysis offline."""
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    counts = {}
    for table in (store.vmarket, store.vquote, store.vpred, store.ingest_run):
        rows = store.read_table(engine, table)
        cols = [c.name for c in table.columns]
        pq.write_table(pa.table({c: [r[c] for r in rows] for c in cols}),
                       str(Path(out_dir) / f"{table.name}.parquet"))
        counts[table.name] = len(rows)
    return counts
