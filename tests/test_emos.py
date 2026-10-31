import math
import random

import pytest

from weather_vs_market.model import emos as E


def _synthetic(n=720, w=0.7, b=(1.5, 1.0, -0.5), s0=1.2, k=0.25, seed=0):
    rng = random.Random(seed)
    out = []
    for i in range(n):
        doy = i % 365 + 1
        truth = 70 + 15 * math.sin(2 * math.pi * doy / 365.25) + rng.gauss(0, 2)
        gfs = truth + rng.gauss(0, 3)
        ecmwf = truth + rng.gauss(0, 3)
        mean = w * gfs + (1 - w) * ecmwf + b[0] + b[1] * math.cos(2 * math.pi * doy / 365.25) \
            + b[2] * math.sin(2 * math.pi * doy / 365.25)
        sd = math.sqrt(s0 ** 2 + k * (gfs - ecmwf) ** 2)
        out.append(E.Sample("KNYC", 1, gfs, ecmwf, mean + rng.gauss(0, sd), doy))
    return out


def test_fit_recovers_weight_seasonal_bias_and_spread():
    # n large enough that sampling error (SE of w ~0.017 here) sits well inside the tolerances
    p = E.fit(_synthetic(n=3000))[("KNYC", 1)]
    assert p.w == pytest.approx(0.7, abs=0.05)
    assert (p.b0, p.b1, p.b2) == pytest.approx((1.5, 1.0, -0.5), abs=0.3)
    assert p.k == pytest.approx(0.25, abs=0.1)
    assert math.sqrt(p.s0sq) == pytest.approx(1.2, abs=0.4)
    assert p.n == 3000


def test_weight_is_clipped_to_the_unit_interval():
    # observations follow GFS "more than fully": the unclipped weight would exceed 1
    samples = [E.Sample("KMIA", 2, g, e, g + 0.5 * (g - e), d)
               for d, (g, e) in enumerate([(80 + i % 9, 78 + i % 5) for i in range(200)], start=1)]
    assert E.fit(samples)[("KMIA", 2)].w == 1.0


def test_spread_grows_with_model_disagreement_and_has_a_floor():
    p = E.Params(w=0.5, b0=0, b1=0, b2=0, s0sq=0.01, k=0.3, n=100)
    assert E.sigma(p, 80, 80) == E.MIN_SIGMA
    assert E.sigma(p, 90, 80) > E.sigma(p, 84, 80)


def test_ladder_probabilities_sum_to_one():
    p = E.Params(w=0.6, b0=1.0, b1=0.5, b2=0.0, s0sq=2.0, k=0.2, n=100)
    ladder = [(None, 79.0), (80.0, 81.0), (82.0, 83.0), (84.0, None)]
    probs = E.ladder_probs(p, 81.0, 83.0, 200, ladder)
    assert math.isclose(sum(probs), 1.0, rel_tol=1e-9)


def test_too_few_samples_are_skipped_and_json_round_trips():
    assert E.fit(_synthetic(n=30)) == {}
    stored = E.params_to_json(E.fit(_synthetic()))       # rounded to 4 decimals
    assert E.params_to_json(E.params_from_json(stored)) == stored
