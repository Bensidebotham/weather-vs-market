"""Fit and score blend_v1 (docs/PROTOCOL.md, protocol v2).

Weights are fit on training-window events only and frozen in config/; scores
compare the blend with the market on the test window and the forward record.
"""
import json
import logging
import time

from sqlalchemy import Engine

from weather_vs_market.analysis import blend as Bl
from weather_vs_market.analysis import verification as V
from weather_vs_market.config import ROOT, Settings
from weather_vs_market.model import det_gauss as D
from weather_vs_market.pipeline.backtest import SOURCES, TOLERANCE_S
from weather_vs_market.pipeline.fit import TRAIN
from weather_vs_market.pipeline.publish import lead_points
from weather_vs_market.storage import store

log = logging.getLogger("wvm.blend")

MODEL = "blend_v1"
WEIGHTS_FILE = ROOT / "config" / "blend_v1.params.json"
RESULTS_DIR = ROOT / "results"


def events_for(settings: Settings, engine: Engine, venue: str, window: tuple[str, str]) -> list[dict]:
    return V.event_frame(engine, venue=venue, model=D.MODEL, lead_points=lead_points(settings),
                         tz_for_city=settings.city_timezones(venue), quote_sources=(SOURCES[venue],),
                         tolerance_s=TOLERANCE_S, date_range=window)


def run_fit(settings: Settings, engine: Engine, n_boot: int = 500) -> dict:
    weights: dict = {}
    for venue in SOURCES:
        events = events_for(settings, engine, venue, TRAIN)
        weights[venue] = {}
        for lp in lead_points(settings):
            rows = [e for e in events if e["lead"] == lp.name]
            if not rows:
                continue
            a, b, loss = Bl.fit_weights(rows)
            b_ci = Bl.bootstrap_b(rows, n_boot=n_boot)
            weights[venue][lp.name] = {"a": a, "b": b, "b_ci": b_ci, "log_loss": round(loss, 4),
                                       "n_events": len(rows)}
            log.info("%s %s: a=%.2f b=%.2f b_ci=%s n=%d", venue, lp.name, a, b, b_ci, len(rows))
    doc = {"model": MODEL, "train_window": list(TRAIN), "fit_ts": time.time(), "weights": weights}
    WEIGHTS_FILE.write_text(json.dumps(doc, indent=2) + "\n")
    return doc


def load_weights() -> dict:
    return json.loads(WEIGHTS_FILE.read_text())["weights"]


def run_score(settings: Settings, engine: Engine, window: tuple[str, str], name: str) -> dict:
    weights = load_weights()
    order = [lp.name for lp in lead_points(settings)]
    doc = {"model": MODEL, "window_name": name, "window": list(window), "train_window": list(TRAIN),
           "generated_ts": time.time(), "weights": weights, "venues": {}}
    for venue in SOURCES:
        w = {lead: (v["a"], v["b"]) for lead, v in weights.get(venue, {}).items()}
        rows = Bl.blend_rows(events_for(settings, engine, venue, window), w)
        doc["venues"][venue] = {"summary": V.summarize(rows, order=order) if rows else []}
    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / f"blend_{name}.json").write_text(json.dumps(doc, indent=1) + "\n")
    store.save_result(engine, f"blend_{name}", doc, generated_ts=doc["generated_ts"])
    return doc
