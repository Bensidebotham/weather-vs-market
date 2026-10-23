"""blend_v1: does the model add information the market price lacks? (docs/PROTOCOL.md, v2)

A logarithmic opinion pool over each ladder, p(k) ∝ p_market(k)^a · p_model(k)^b,
with both sides floored before pooling. a = 1, b = 0 reproduces the market, so
the fitted b measures how much the model is worth on top of the price.
"""
import math
import random

import numpy as np

from weather_vs_market.analysis.verification import PROB_FLOOR, brier, rps

GRID = np.round(np.arange(0.0, 2.0 + 1e-9, 0.05), 2)


def pool(market: list[float], model: list[float], a: float, b: float) -> list[float]:
    logs = [a * math.log(max(m, PROB_FLOOR)) + b * math.log(max(q, PROB_FLOOR))
            for m, q in zip(market, model, strict=True)]
    top = max(logs)
    w = [math.exp(x - top) for x in logs]
    s = sum(w)
    return [x / s for x in w]


def _arrays(events: list[dict]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Log-prob matrices padded to the widest ladder, a validity mask, and winner indices."""
    width = max(len(e["market_probs"]) for e in events)
    lm = np.zeros((len(events), width))
    lq = np.zeros((len(events), width))
    mask = np.zeros((len(events), width), dtype=bool)
    win = np.zeros(len(events), dtype=int)
    for i, e in enumerate(events):
        k = len(e["market_probs"])
        lm[i, :k] = np.log(np.maximum(e["market_probs"], PROB_FLOOR))
        lq[i, :k] = np.log(np.maximum(e["model_probs"], PROB_FLOOR))
        mask[i, :k] = True
        win[i] = e["outcomes"].index(1)
    return lm, lq, mask, win


def _grid_losses(lm, lq, mask, win) -> np.ndarray:
    """Mean -log p(winner) for every (a, b) on the grid: shape (len(GRID), len(GRID))."""
    rows = np.arange(len(win))
    out = np.empty((len(GRID), len(GRID)))
    for i, a in enumerate(GRID):
        for j, b in enumerate(GRID):
            z = np.where(mask, a * lm + b * lq, -np.inf)
            zmax = z.max(axis=1, keepdims=True)
            lse = zmax[:, 0] + np.log(np.exp(z - zmax).sum(axis=1))
            out[i, j] = np.mean(lse - z[rows, win])
    return out


def _best(losses: np.ndarray) -> tuple[float, float, float]:
    """Grid minimum; ties go to the smallest model weight, then the smallest market
    weight, so a model that adds nothing gets b = 0."""
    best = np.min(losses)
    for j in range(len(GRID)):                 # b ascending
        for i in range(len(GRID)):             # a ascending
            if losses[i, j] <= best + 1e-12:
                return float(GRID[i]), float(GRID[j]), float(best)
    raise AssertionError("unreachable")


def fit_weights(events: list[dict]) -> tuple[float, float, float]:
    """(a, b, mean log loss) minimizing the winning-bucket log loss over the grid."""
    return _best(_grid_losses(*_arrays(events)))


def bootstrap_b(events: list[dict], n_boot: int = 500, seed: int = 0) -> list[float]:
    """95% interval for the model weight b, resampling events."""
    rng = random.Random(seed)
    events = sorted(events, key=lambda e: e.get("event_key", ""))
    lm, lq, mask, win = _arrays(events)
    bs = []
    for _ in range(n_boot):
        idx = np.array([rng.randrange(len(events)) for _ in range(len(events))])
        bs.append(_best(_grid_losses(lm[idx], lq[idx], mask[idx], win[idx]))[1])
    bs.sort()
    return [bs[int(0.025 * (n_boot - 1))], bs[int(0.975 * (n_boot - 1))]]


def blend_rows(events: list[dict], weights: dict[str, tuple[float, float]]) -> list[dict]:
    """Rows shaped for verification.summarize, with the blend in the "model" columns."""
    rows = []
    for e in events:
        if e["lead"] not in weights:
            continue
        a, b = weights[e["lead"]]
        p = pool(e["market_probs"], e["model_probs"], a, b)
        winner = e["outcomes"].index(1)
        m = e["market_probs"]
        rows.append({
            "lead": e["lead"], "event_key": e.get("event_key", ""),
            "model_brier": sum(brier(x, o) for x, o in zip(p, e["outcomes"], strict=True)),
            "market_brier": sum(brier(x, o) for x, o in zip(m, e["outcomes"], strict=True)),
            "model_rps": rps(p, winner), "market_rps": rps(m, winner),
            "model_logscore": -math.log(max(p[winner], PROB_FLOOR)),
            "market_logscore": -math.log(max(m[winner], PROB_FLOOR)),
        })
    return rows
