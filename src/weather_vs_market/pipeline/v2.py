"""Fit, forecast and score emos_v2 (docs/PROTOCOL.md, protocol v3).

Fitting reads only the public archives (Open-Meteo, IEM), never the database.
Scoring covers the forward record only, against the market and, on the same
city-days, against det_gauss_v1.
"""
import json
import logging
import time
from datetime import date, timedelta

from sqlalchemy import Engine

from weather_vs_market.analysis import verification as V
from weather_vs_market.config import ROOT, Settings
from weather_vs_market.forecast import previous_runs
from weather_vs_market.model import det_gauss as D
from weather_vs_market.model import emos as E
from weather_vs_market.pipeline.backtest import SOURCES, TOLERANCE_S
from weather_vs_market.pipeline.fit import TRAIN, VENUE_TRUTH, observed_highs, settlement_stations
from weather_vs_market.pipeline.publish import lead_points
from weather_vs_market.storage import store

log = logging.getLogger("wvm.v2")

PARAMS_FILE = ROOT / "config" / "emos_v2.params.json"
RESULTS_DIR = ROOT / "results"
GFS, ECMWF = D.MODELS


def samples_for_station(settings: Settings, station_id: str, start: str, end: str,
                        leads: tuple[int, ...], truth: str) -> list[E.Sample]:
    st = settings.station(station_id)
    highs = observed_highs(truth, station_id, start, end, st.tz)
    maxima = previous_runs.fetch_daily_max_by_lead(st.lat, st.lon, st.tz, start, end, leads=leads,
                                                   models=D.MODELS)
    out = []
    for day, high in sorted(highs.items()):
        if not start <= day <= end:
            continue
        for lead in leads:
            gfs, ecmwf = maxima.get((day, GFS, lead)), maxima.get((day, ECMWF, lead))
            if gfs is not None and ecmwf is not None:
                doy = date.fromisoformat(day).timetuple().tm_yday
                out.append(E.Sample(station_id, lead, gfs, ecmwf, float(high), doy))
    return out


def run_fit(settings: Settings) -> dict:
    leads = tuple(sorted({lp.previous_run_days for lp in settings.evaluation.lead_points}))
    params = {}
    for venue, truth in VENUE_TRUTH.items():
        samples: list[E.Sample] = []
        for station_id in settlement_stations(settings, venue):
            s = samples_for_station(settings, station_id, *TRAIN, leads, truth)
            log.info("%s %s: %d training samples", truth, station_id, len(s))
            samples += s
        params[truth] = E.params_to_json(E.fit(samples))
    doc = {"model": E.MODEL, "train_window": list(TRAIN), "fit_at": date.today().isoformat(),
           "truth_by_venue": VENUE_TRUTH, "params": params}
    PARAMS_FILE.write_text(json.dumps(doc, indent=2) + "\n")
    return doc


def load_params(truth: str) -> dict[tuple[str, int], E.Params]:
    return E.params_from_json(json.loads(PARAMS_FILE.read_text())["params"][truth])


def forecast(settings: Settings, engine: Engine, start: str, end: str) -> dict:
    """emos_v2 predictions at each lead point for stored ladders, replacing earlier ones."""
    lps = settings.evaluation.lead_points
    leads = tuple(sorted({lp.previous_run_days for lp in lps}))
    v = store.vmarket
    groups: dict[tuple[str, str], list[dict]] = {}
    for m in store.read_markets(engine, v.c.target_date >= start, v.c.target_date <= end,
                                v.c.venue.in_(list(VENUE_TRUTH))):
        if m["station"]:
            groups.setdefault((m["venue"], m["station"]), []).append(m)
    first = (date.fromisoformat(start) - timedelta(days=1)).isoformat()
    maxima_cache: dict[str, dict] = {}
    counts = {"preds": 0, "skipped": 0}
    for (venue, station_id), markets in sorted(groups.items()):
        params = load_params(VENUE_TRUTH[venue])
        st = settings.station(station_id)
        if station_id not in maxima_cache:
            maxima_cache[station_id] = previous_runs.fetch_daily_max_by_lead(
                st.lat, st.lon, st.tz, first, end, leads=leads, models=D.MODELS)
        maxima = maxima_cache[station_id]
        ladders: dict[str, list[dict]] = {}
        for m in markets:
            ladders.setdefault(m["event_key"], []).append(m)
        preds = []
        for ladder in ladders.values():
            d = ladder[0]["target_date"]
            for lp in lps:
                n = lp.previous_run_days
                p = params.get((station_id, n))
                gfs, ecmwf = maxima.get((d, GFS, n)), maxima.get((d, ECMWF, n))
                if p is None or gfs is None or ecmwf is None:
                    counts["skipped"] += 1
                    continue
                ts = V.LeadPoint(lp.name, lp.day_offset, lp.hour).timestamp(d, st.tz) - 1
                doy = date.fromisoformat(d).timetuple().tm_yday
                probs = E.ladder_probs(p, gfs, ecmwf, doy, [(m["bucket_lo"], m["bucket_hi"]) for m in ladder])
                preds += [{"ts": ts, "market_uid": m["market_uid"], "model": E.MODEL, "model_prob": prob,
                           "lead_hours": ((m["close_ts"] or ts) - ts) / 3600}
                          for m, prob in zip(ladder, probs, strict=True)]
        store.delete_preds(engine, E.MODEL, [m["market_uid"] for m in markets])
        store.insert_preds(engine, preds)
        counts["preds"] += len(preds)
    return counts


_SCORES = ("brier", "rps", "logscore")


def head_to_head(v2_events: list[dict], v1_events: list[dict]) -> list[dict]:
    """Rows for verification.summarize with v2 in the model columns and v1 in the market ones."""
    v1 = {(e["event_key"], e["lead"]): e for e in v1_events}
    rows = []
    for e in v2_events:
        other = v1.get((e["event_key"], e["lead"]))
        if other is None:
            continue
        row = {"event_key": e["event_key"], "lead": e["lead"]}
        for k in _SCORES:
            row[f"model_{k}"], row[f"market_{k}"] = e[f"model_{k}"], other[f"model_{k}"]
        rows.append(row)
    return rows


def score(settings: Settings, engine: Engine, window: tuple[str, str], name: str) -> dict:
    lps = lead_points(settings)
    order = [lp.name for lp in lps]
    doc = {"model": E.MODEL, "protocol": "v3", "window_name": name, "window": list(window),
           "generated_ts": time.time(), "venues": {}}
    for venue, source in SOURCES.items():
        def frame(model: str, venue: str = venue, source: str = source) -> list[dict]:
            return V.event_frame(engine, venue=venue, model=model, lead_points=lps,
                                 tz_for_city=settings.city_timezones(venue), quote_sources=(source,),
                                 tolerance_s=TOLERANCE_S, date_range=window)
        v2_events, v1_events = frame(E.MODEL), frame(D.MODEL)
        pairs = head_to_head(v2_events, v1_events)
        doc["venues"][venue] = {
            "vs_market": V.summarize(v2_events, order=order) if v2_events else [],
            "vs_v1": V.summarize(pairs, order=order) if pairs else [],
        }
    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / f"emos_{name}.json").write_text(json.dumps(doc, indent=1) + "\n")
    store.save_result(engine, f"emos_{name}", doc, generated_ts=doc["generated_ts"])
    return doc
