import math

import pytest

from weather_vs_market.analysis import blend as Bl


def _ev(market, model, winner, lead="L", key="E"):
    return {"lead": lead, "event_key": key, "market_probs": market, "model_probs": model,
            "outcomes": [int(i == winner) for i in range(len(market))]}


def test_pool_with_market_weight_one_and_model_zero_is_the_market():
    assert Bl.pool([0.2, 0.5, 0.3], [0.9, 0.05, 0.05], 1.0, 0.0) == pytest.approx([0.2, 0.5, 0.3])


def test_pool_is_normalized_and_floors_zeros():
    p = Bl.pool([0.0, 0.5, 0.5], [0.5, 0.5, 0.0], 1.0, 1.0)
    assert math.isclose(sum(p), 1.0) and min(p) > 0


def test_fit_recovers_zero_model_weight_when_the_model_is_noise():
    # market always right-ish, model random: best blend ignores the model
    events = [_ev([0.1, 0.8, 0.1], [0.6, 0.2, 0.2] if i % 2 else [0.2, 0.2, 0.6], 1, key=f"E{i}")
              for i in range(40)]
    a, b, _ = Bl.fit_weights(events)
    assert b == 0.0 and a > 0


def test_fit_uses_the_model_when_it_knows_something_the_market_does_not():
    # market flat, model points at the winner: the model gets weight
    events = [_ev([1 / 3] * 3, [0.1, 0.8, 0.1], 1, key=f"E{i}") for i in range(30)]
    events += [_ev([1 / 3] * 3, [0.4, 0.3, 0.3], 0, key=f"F{i}") for i in range(10)]
    _, b, _ = Bl.fit_weights(events)
    assert b > 0.5


def test_ladders_of_different_sizes_fit_together():
    events = [_ev([0.2, 0.8], [0.5, 0.5], 1, key="A"), _ev([0.1, 0.1, 0.8], [0.3, 0.3, 0.4], 2, key="B")]
    a, b, loss = Bl.fit_weights(events)
    assert 0 <= a <= 2 and 0 <= b <= 2 and loss > 0


def test_blend_rows_score_blend_against_market():
    rows = Bl.blend_rows([_ev([0.2, 0.6, 0.2], [0.1, 0.8, 0.1], 1)], {"L": (1.0, 1.0)})
    r = rows[0]
    assert r["market_brier"] == pytest.approx(0.04 + 0.16 + 0.04)
    assert r["model_brier"] < r["market_brier"]      # "model" columns hold the blend


def test_fit_and_score_pipeline_stores_weights_and_results(monkeypatch, tmp_path):
    from weather_vs_market.config import load_settings
    from weather_vs_market.pipeline import blend as PB
    from weather_vs_market.storage import store as S
    engine = S.connect(str(tmp_path / "v.sqlite3"))
    events = [_ev([0.1, 0.8, 0.1], [0.2, 0.6, 0.2], 1, lead=lead, key=f"E{i}")
              for i in range(20) for lead in ("D-1 12:00", "D 08:00")]
    monkeypatch.setattr(PB, "events_for", lambda s, e, venue, w: events if venue == "kalshi" else [])
    monkeypatch.setattr(PB, "WEIGHTS_FILE", tmp_path / "blend.json")
    monkeypatch.setattr(PB, "RESULTS_DIR", tmp_path / "results")
    fit = PB.run_fit(load_settings(), engine, n_boot=20)
    assert set(fit["weights"]["kalshi"]) == {"D-1 12:00", "D 08:00"}
    doc = PB.run_score(load_settings(), engine, ("2026-10-01", "2026-10-20"), "forward")
    assert [r["lead"] for r in doc["venues"]["kalshi"]["summary"]] == ["D-1 12:00", "D 08:00"]
    assert S.load_result(engine, "blend_forward")["model"] == "blend_v1"
