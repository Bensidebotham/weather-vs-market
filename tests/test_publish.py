import pyarrow.parquet as pq

from conftest import market
from weather_vs_market.config import load_settings
from weather_vs_market.pipeline import publish as P
from weather_vs_market.storage import store as S


def test_publish_stores_doc_for_dashboard(engine, tmp_path):
    S.upsert_markets(engine, [market()])
    out = tmp_path / "e.json"
    doc = P.publish(load_settings(), engine, out_file=str(out))
    assert doc["schema_version"] == P.SCHEMA_VERSION
    assert S.latest_published(engine)["generated_ts"] == doc["generated_ts"]
    assert set(doc) >= {"backtest", "live", "tracking", "live_disagreements"}
    assert doc["tracking"]["n_markets"] == 1
    assert out.exists()


def test_dump_tables_writes_parquet(engine, tmp_path):
    S.upsert_markets(engine, [market()])
    counts = P.dump_tables(engine, str(tmp_path / "dump"))
    assert counts["vmarket"] == 1
    assert pq.read_table(str(tmp_path / "dump" / "vmarket.parquet")).num_rows == 1


def test_publish_includes_the_stored_forward_record(engine):
    S.save_result(engine, "forward", {"window_name": "forward", "venues": {}}, generated_ts=1.0)
    doc = P.build_doc(load_settings(), engine)
    assert doc["forward"]["window_name"] == "forward"


def test_live_scores_are_reused_within_six_hours(engine, monkeypatch):
    calls = []
    monkeypatch.setattr(P, "live_scores", lambda s, e: calls.append(1) or {"kalshi": {"n_events": 0}})
    settings = load_settings()
    P.build_doc(settings, engine, now=1_000_000.0)
    P.build_doc(settings, engine, now=1_000_000.0 + 3600)
    assert len(calls) == 1
    P.build_doc(settings, engine, now=1_000_000.0 + 7 * 3600)
    assert len(calls) == 2
