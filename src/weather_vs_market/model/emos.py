"""emos_v2: ensemble model output statistics on GFS + ECMWF (docs/PROTOCOL.md, v3).

Aimed at det_gauss_v1's diagnosed failures:

    mean = w·GFS + (1 − w)·ECMWF + b0 + b1·cos(2π·doy/365.25) + b2·sin(2π·doy/365.25)
    σ²   = s0² + k·(GFS − ECMWF)²

The weight lets one model count for more where it has been better, the harmonic
terms let the bias follow the seasons, and the spread widens on days the two
models disagree, which is where v1 was confidently wrong. Fit per settlement
truth, station and lead on the training window only, in the style of Gneiting
et al. (2005).
"""
import math
from dataclasses import dataclass

import numpy as np

from weather_vs_market.model.buckets import bucket_probability

MODEL = "emos_v2"
MIN_SIGMA = 0.75     # °F, same floor as v1
YEAR = 365.25


@dataclass(frozen=True)
class Sample:
    station: str
    lead_days: int
    gfs: float
    ecmwf: float
    observed: float
    doy: int


@dataclass(frozen=True)
class Params:
    w: float
    b0: float
    b1: float
    b2: float
    s0sq: float
    k: float
    n: int


def _season(doy) -> tuple:
    angle = 2 * np.pi * np.asarray(doy, dtype=float) / YEAR
    return np.cos(angle), np.sin(angle)


def _fit_group(rows: list[Sample]) -> Params:
    gfs = np.array([r.gfs for r in rows])
    ecmwf = np.array([r.ecmwf for r in rows])
    obs = np.array([r.observed for r in rows])
    cos, sin = _season([r.doy for r in rows])
    d = gfs - ecmwf
    ones = np.ones_like(d)
    # obs − ECMWF = w·(GFS − ECMWF) + b0 + b1·cos + b2·sin
    beta = np.linalg.lstsq(np.column_stack([d, ones, cos, sin]), obs - ecmwf, rcond=None)[0]
    w = float(beta[0])
    if not 0.0 <= w <= 1.0:
        w = min(max(w, 0.0), 1.0)
        beta = np.concatenate([[w], np.linalg.lstsq(np.column_stack([ones, cos, sin]),
                                                    obs - ecmwf - w * d, rcond=None)[0]])
    b0, b1, b2 = (float(x) for x in beta[1:])
    resid = obs - (ecmwf + w * d + b0 + b1 * cos + b2 * sin)
    # resid² = s0² + k·d²
    s0sq, k = (float(x) for x in np.linalg.lstsq(np.column_stack([ones, d ** 2]), resid ** 2, rcond=None)[0])
    if k < 0:
        k, s0sq = 0.0, float(np.mean(resid ** 2))
    return Params(w=w, b0=b0, b1=b1, b2=b2, s0sq=max(s0sq, 0.0), k=k, n=len(rows))


def fit(samples: list[Sample], min_samples: int = 60) -> dict[tuple[str, int], Params]:
    groups: dict[tuple[str, int], list[Sample]] = {}
    for s in samples:
        groups.setdefault((s.station, s.lead_days), []).append(s)
    return {key: _fit_group(rows) for key, rows in groups.items() if len(rows) >= min_samples}


def mean(p: Params, gfs: float, ecmwf: float, doy: int) -> float:
    angle = 2 * math.pi * doy / YEAR
    return p.w * gfs + (1 - p.w) * ecmwf + p.b0 + p.b1 * math.cos(angle) + p.b2 * math.sin(angle)


def sigma(p: Params, gfs: float, ecmwf: float) -> float:
    return max(math.sqrt(p.s0sq + p.k * (gfs - ecmwf) ** 2), MIN_SIGMA)


def ladder_probs(p: Params, gfs: float, ecmwf: float, doy: int,
                 ladder: list[tuple[float | None, float | None]]) -> list[float]:
    mu, sd = mean(p, gfs, ecmwf, doy), sigma(p, gfs, ecmwf)
    return [bucket_probability([mu], lo, hi, sigma=sd) for lo, hi in ladder]


def params_to_json(params: dict[tuple[str, int], Params]) -> list[dict]:
    return [{"station": st, "lead_days": lead, "w": round(p.w, 4), "b0": round(p.b0, 4),
             "b1": round(p.b1, 4), "b2": round(p.b2, 4), "s0sq": round(p.s0sq, 4), "k": round(p.k, 4),
             "n": p.n} for (st, lead), p in sorted(params.items())]


def params_from_json(rows: list[dict]) -> dict[tuple[str, int], Params]:
    return {(r["station"], r["lead_days"]):
            Params(r["w"], r["b0"], r["b1"], r["b2"], r["s0sq"], r["k"], r["n"]) for r in rows}
