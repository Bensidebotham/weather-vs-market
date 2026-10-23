from weather_vs_market.forecast import obs


def _nws(ts_utc, temp_c):
    return {"properties": {"timestamp": ts_utc, "temperature": {"value": temp_c}}}


def test_nws_features_become_local_fahrenheit_readings_for_the_day():
    feats = [_nws("2026-10-22T18:51:00+00:00", 18.9),       # 14:51 EDT
             _nws("2026-10-23T04:51:00+00:00", 10.0),       # next local day
             _nws("2026-10-22T19:51:00+00:00", None)]
    assert obs.parse_nws(feats, "America/New_York", "2026-10-22") == [("2026-10-22T14:51", 66.02)]


def test_readings_merge_sources_and_running_max_takes_the_highest():
    iem = [("2026-10-22T14:51", 66.0)]
    nws = [("2026-10-22T14:51", 65.9), ("2026-10-22T07:51", 50.0)]
    readings = obs.merge(iem, nws)
    assert obs.running_max(readings) == 66.0
    assert obs.running_max([]) is None


def test_peak_coverage_requires_most_afternoon_hours():
    # 2026-10-22 KNYC from api.weather.gov: readings stopped at 08:51 and resumed at 19:51,
    # so the 61F "running max" missed the 66F peak. That day must not count as locked.
    gappy = [(f"2026-10-22T{h:02d}:51", 55.0) for h in (0, 1, 2, 7, 8, 19)]
    full = [(f"2026-10-22T{h:02d}:51", 55.0) for h in range(0, 20)]
    assert not obs.peak_covered(gappy)
    assert obs.peak_covered(full)
