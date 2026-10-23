"""Ensemble members via open-meteo (free, no key): the live uncertainty signal.

GFS (31 members) + ECMWF IFS (51 members) give a distribution over the
daily high, not just a point estimate. Open-Meteo keeps no archive of past
ensemble runs, so this model can only be scored forward, on live snapshots.
"""

import logging

import httpx

from weather_vs_market import http

log = logging.getLogger("wvm.ensemble")

ENSEMBLE_BASE = "https://ensemble-api.open-meteo.com/v1/ensemble"
MODELS = "gfs025,ecmwf_ifs025"


_CACHE: dict[tuple, list[dict]] = {}


def clear_cache() -> None:
    _CACHE.clear()


def _fetch(lat: float, lon: float, tz: str, unit: str, client: httpx.Client | None) -> list[dict] | None:
    """All models' 7-day hourly members for one location, fetched once per process.

    One request covers every target date, so a cycle asks Open-Meteo once per
    station rather than once per (station, date): shared CI runners were being
    rate-limited. Failures are logged, not cached, and return None.
    """
    key = (round(lat, 4), round(lon, 4), tz, unit.upper())
    if key in _CACHE:
        return _CACHE[key]
    params = {"latitude": lat, "longitude": lon, "hourly": "temperature_2m", "models": MODELS,
              "timezone": tz, "forecast_days": 7}
    if unit.upper() == "F":
        params["temperature_unit"] = "fahrenheit"
    try:
        with http.session(client) as c:
            payload = http.get(c, ENSEMBLE_BASE, params, max_tries=5, backoff_s=2.0).json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("ensemble fetch failed for %.4f,%.4f: %s", lat, lon, e)
        return None
    _CACHE[key] = payload if isinstance(payload, list) else [payload]
    return _CACHE[key]


def get_ensemble_members(
    lat: float, lon: float, tz: str, target_date: str, unit: str = "F",
    client: httpx.Client | None = None,
) -> list[float]:
    """Predicted daily-high temps for target_date, one per ensemble member.

    Returns [] on error or if the horizon doesn't cover the date.
    """
    payloads = _fetch(lat, lon, tz, unit, client)
    if payloads is None:
        return []


    members: list[float] = []
    for payload in payloads:
        hourly = payload.get("hourly", {})
        times = hourly.get("time", [])
        day_idx = [i for i, t in enumerate(times) if t.startswith(target_date)]
        if not day_idx:
            continue
        for key, series in hourly.items():
            if not key.startswith("temperature_2m"):
                continue
            vals = [series[i] for i in day_idx if series[i] is not None]
            if vals:
                members.append(max(vals))
    return members
