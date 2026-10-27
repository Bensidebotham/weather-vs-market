"""Keep the live tables small: drop live snapshots nothing will ever read.

Once a market settles, live scoring only uses the latest snapshot at or before
each lead point (verification.event_frame's as-of join). Every other live quote
and live-model prediction for that market is dead weight on Neon's free tier, so
this deletes them. Open markets, backtest sources and other models are untouched,
and live scores are identical before and after.
"""
import logging

from sqlalchemy import Engine, and_, delete, not_

from weather_vs_market.analysis.verification import LeadPoint
from weather_vs_market.pipeline.ingest import ENSEMBLE_MODEL
from weather_vs_market.storage import store

log = logging.getLogger("wvm.compact")

LIVE_SOURCE = "live"


def keep_ts(timestamps: list[float], point_ts: list[float]) -> set[float]:
    """The latest timestamp at or before each lead point."""
    keep = set()
    for pts in point_ts:
        before = [t for t in timestamps if t <= pts]
        if before:
            keep.add(max(before))
    return keep


def _delete_except(engine: Engine, table, kind_clause, keep: dict[str, set[float]]) -> int:
    deleted = 0
    with engine.begin() as c:
        for uid, ts in keep.items():
            cond = [table.c.market_uid == uid, kind_clause]
            if ts:
                cond.append(not_(table.c.ts.in_(sorted(ts))))
            deleted += c.execute(delete(table).where(and_(*cond))).rowcount or 0
    return deleted


def compact_live(engine: Engine, lead_points: list[LeadPoint], tz_for_city: dict[str, str]) -> dict:
    v, q, p = store.vmarket, store.vquote, store.vpred
    live_uids = (store.distinct_uids(engine, q, q.c.source == LIVE_SOURCE)
                 | store.distinct_uids(engine, p, p.c.model == ENSEMBLE_MODEL))
    markets = [m for m in store.read_markets(engine, v.c.settled == 1, v.c.market_uid.in_(sorted(live_uids)))
               if m["city"] in tz_for_city] if live_uids else []
    if not markets:
        return {"markets": 0, "quotes_deleted": 0, "preds_deleted": 0}
    uids = [m["market_uid"] for m in markets]
    quote_ts: dict[str, list[float]] = {}
    for r in store.read_quotes(engine, q.c.source == LIVE_SOURCE, q.c.market_uid.in_(uids)):
        quote_ts.setdefault(r["market_uid"], []).append(r["ts"])
    pred_ts: dict[str, list[float]] = {}
    for r in store.read_preds(engine, p.c.model == ENSEMBLE_MODEL, p.c.market_uid.in_(uids)):
        pred_ts.setdefault(r["market_uid"], []).append(r["ts"])
    keep_q, keep_p = {}, {}
    for m in markets:
        points = [lp.timestamp(m["target_date"], tz_for_city[m["city"]]) for lp in lead_points]
        keep_q[m["market_uid"]] = keep_ts(quote_ts.get(m["market_uid"], []), points)
        keep_p[m["market_uid"]] = keep_ts(pred_ts.get(m["market_uid"], []), points)
    out = {"markets": len(markets),
           "quotes_deleted": _delete_except(engine, q, q.c.source == LIVE_SOURCE, keep_q),
           "preds_deleted": _delete_except(engine, p, p.c.model == ENSEMBLE_MODEL, keep_p)}
    log.info("compacted %s", out)
    return out


