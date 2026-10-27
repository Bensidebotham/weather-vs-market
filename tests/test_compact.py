from conftest import market
from weather_vs_market.analysis import verification as V
from weather_vs_market.pipeline import compact as C
from weather_vs_market.pipeline.ingest import ENSEMBLE_MODEL
from weather_vs_market.storage import store as S

TZ = {"New York": "America/New_York"}
LEADS = [V.LeadPoint("D-1 12:00", -1, 12), V.LeadPoint("D 08:00", 0, 8)]


def test_keep_the_latest_snapshot_at_or_before_each_lead_point():
    assert C.keep_ts([10.0, 20.0, 30.0, 40.0, 50.0], [25.0, 45.0]) == {20.0, 40.0}
    assert C.keep_ts([30.0], [25.0]) == set()


def _seed(engine, uid, settled, ladder_event="EV"):
    S.upsert_markets(engine, [market(uid, event_key=ladder_event, target_date="2026-10-20",
                                     bucket_lo=None, bucket_hi=None)])
    pts = [lp.timestamp("2026-10-20", "America/New_York") for lp in LEADS]
    # hourly snapshots across both lead points, plus some after
    times = [pts[0] - 3 * 3600 + h * 3600 for h in range(30)]
    S.insert_quotes(engine, [{"ts": t, "market_uid": uid, "market_prob": 0.5 + (t % 7) / 100,
                              "best_bid": None, "best_ask": None, "source": "live"} for t in times])
    S.insert_preds(engine, [{"ts": t, "market_uid": uid, "model": ENSEMBLE_MODEL,
                             "model_prob": 0.4 + (t % 5) / 100, "lead_hours": 1.0} for t in times])
    if settled:
        S.settle_markets(engine, [(uid, 1)])
    return len(times)


def test_compaction_keeps_scores_identical_and_drops_the_rest(engine):
    n = _seed(engine, "kalshi:SET", settled=True)
    kwargs = dict(venue="kalshi", model=ENSEMBLE_MODEL, lead_points=LEADS, tz_for_city=TZ,
                  quote_sources=("live",), quoted_events_only=True)
    before = V.event_frame(engine, **kwargs)
    out = C.compact_live(engine, LEADS, TZ)
    assert V.event_frame(engine, **kwargs) == before and len(before) == 2
    assert out == {"markets": 1, "quotes_deleted": n - 2, "preds_deleted": n - 2}
    assert len(S.read_quotes(engine)) == 2 and len(S.read_preds(engine)) == 2


def test_open_markets_and_other_sources_are_untouched(engine):
    n = _seed(engine, "kalshi:OPEN", settled=False, ladder_event="EV2")
    S.insert_quotes(engine, [{"ts": 1.0, "market_uid": "kalshi:OPEN", "market_prob": 0.5,
                              "best_bid": None, "best_ask": None, "source": "kalshi_candles"}])
    C.compact_live(engine, LEADS, TZ)
    assert len(S.read_quotes(engine)) == n + 1 and len(S.read_preds(engine)) == n
