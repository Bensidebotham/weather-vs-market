"""Live station observations: the lock-in signal.

The day's high is physically monotone: once the station has observed T, the
settled max cannot be below T, so buckets below the running max can't win.
After the afternoon peak (lock_hour_local) the max is treated as final, but
only if the readings actually cover the peak hours: on 2026-10-22
api.weather.gov returned no KNYC readings from 08:51 to 19:51 local, and a
"locked" 61F running max put 100% on a bucket the 66F afternoon had ruled out.

Readings merge two feeds: IEM's METAR archive (routine + specials, the same
source the locked-day bias was fit on) and api.weather.gov. A failure in one
feed falls back to the other.
"""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from weather_vs_market import http
from weather_vs_market.forecast import iem

log = logging.getLogger("wvm.obs")

NWS_BASE = "https://api.weather.gov"
PEAK_HOURS = range(10, 18)   # local hours in which the daily max almost always falls
MIN_PEAK_HOURS = 6           # of those 8, how many need a reading before the day can lock

Reading = tuple[str, float]  # (local "YYYY-MM-DDTHH:MM", °F)


def parse_nws(features: list[dict], tz: str, target_date: str) -> list[Reading]:
    zone = ZoneInfo(tz)
    out = []
    for f in features:
        props = f.get("properties", {})
        val_c = (props.get("temperature") or {}).get("value")
        if val_c is None or not props.get("timestamp"):
            continue
        local = datetime.fromisoformat(props["timestamp"].replace("Z", "+00:00")).astimezone(zone)
        if local.strftime("%Y-%m-%d") == target_date:
            out.append((local.strftime("%Y-%m-%dT%H:%M"), round(val_c * 9 / 5 + 32, 2)))
    return out


def fetch_nws(station: str, tz: str, target_date: str, client: httpx.Client | None = None) -> list[Reading]:
    day_start = datetime.strptime(target_date, "%Y-%m-%d").replace(tzinfo=ZoneInfo(tz))
    params = {"start": (day_start - timedelta(hours=1)).isoformat(), "limit": 200}
    with http.session(client) as c:
        resp = http.get(c, f"{NWS_BASE}/stations/{station}/observations", params, max_tries=3)
    return parse_nws(resp.json().get("features", []), tz, target_date)


def merge(*feeds: list[Reading]) -> list[Reading]:
    """Union of readings, keeping the higher value when two feeds share a timestamp."""
    best: dict[str, float] = {}
    for feed in feeds:
        for ts, t in feed:
            best[ts] = max(best.get(ts, t), t)
    return sorted(best.items())


def day_readings(station: str, tz: str, target_date: str) -> list[Reading]:
    feeds = []
    for name, fetch in (("iem", lambda: iem.fetch_hourly_temps(station, target_date, target_date, tz)),
                        ("nws", lambda: fetch_nws(station, tz, target_date))):
        try:
            feeds.append([r for r in fetch() if r[0].startswith(target_date)])
        except (httpx.HTTPError, ValueError) as e:
            log.warning("%s readings failed for %s %s: %s", name, station, target_date, e)
    return merge(*feeds)


def running_max(readings: list[Reading]) -> float | None:
    return max((t for _, t in readings), default=None)


def peak_covered(readings: list[Reading]) -> bool:
    hours = {int(ts[11:13]) for ts, _ in readings}
    return len(hours & set(PEAK_HOURS)) >= MIN_PEAK_HOURS


def is_day_locked(tz: str, target_date: str, lock_hour: int) -> bool:
    """True once local time on target_date has passed lock_hour (or the
    date is already past); the daily max is then treated as final."""
    zone = ZoneInfo(tz)
    now = datetime.now(zone)
    today = now.strftime("%Y-%m-%d")
    if target_date < today:
        return True
    if target_date > today:
        return False
    return now.hour >= lock_hour
