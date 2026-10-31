import json

from weather_vs_market.config import load_settings
from weather_vs_market.model import emos as E
from weather_vs_market.pipeline import v2


def _ev(key, lead, brier, rps, log):
    return {"event_key": key, "lead": lead, "model_brier": brier, "model_rps": rps,
            "model_logscore": log, "market_brier": 0.5, "market_rps": 0.1, "market_logscore": 1.0}


def test_head_to_head_pairs_the_same_events_and_puts_v1_in_the_market_columns():
    v2_events = [_ev("A", "L", 0.6, 0.05, 1.5), _ev("B", "L", 0.7, 0.06, 1.6)]
    v1_events = [_ev("A", "L", 0.8, 0.07, 1.9), _ev("C", "L", 0.9, 0.08, 2.0)]
    rows = v2.head_to_head(v2_events, v1_events)
    assert len(rows) == 1
    assert (rows[0]["model_brier"], rows[0]["market_brier"]) == (0.6, 0.8)


def test_samples_use_each_model_and_the_day_of_year(monkeypatch):
    settings = load_settings()
    monkeypatch.setattr(v2, "observed_highs", lambda *a: {"2025-03-01": 60, "2025-03-02": 62})
    monkeypatch.setattr(v2.previous_runs, "fetch_daily_max_by_lead", lambda *a, **k: {
        ("2025-03-01", "gfs_seamless", 1): 58.0, ("2025-03-01", "ecmwf_ifs025", 1): 59.0,
        ("2025-03-02", "gfs_seamless", 1): 61.0})                      # no ECMWF: skipped
    samples = v2.samples_for_station(settings, "KNYC", "2025-03-01", "2025-03-02", (1,), "cli")
    assert samples == [E.Sample("KNYC", 1, 58.0, 59.0, 60.0, 60)]


def test_fit_writes_params_for_each_truth(monkeypatch, tmp_path):
    settings = load_settings()
    monkeypatch.setattr(v2, "PARAMS_FILE", tmp_path / "emos.json")
    monkeypatch.setattr(v2, "samples_for_station", lambda s, st, a, b, leads, truth: [
        E.Sample(st, lead, 70.0 + i % 7, 71.0 + i % 5, 72.0 + i % 3, i % 365 + 1)
        for lead in leads for i in range(80)])
    doc = v2.run_fit(settings)
    stored = json.loads((tmp_path / "emos.json").read_text())
    assert set(stored["params"]) == {"cli", "metar"} and doc["model"] == E.MODEL
    assert {r["station"] for r in stored["params"]["metar"]} >= {"KLGA", "KORD"}
