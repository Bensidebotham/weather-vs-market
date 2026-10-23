import httpx

from weather_vs_market import http
from weather_vs_market.forecast import ensemble

PAYLOAD = {"hourly": {"time": ["2026-10-23T12:00", "2026-10-23T15:00", "2026-10-24T15:00"],
                      "temperature_2m_member01": [60.0, 66.0, 70.0],
                      "temperature_2m_member02": [61.0, 64.0, None]}}


def members(date, client):
    return ensemble.get_ensemble_members(40.0, -74.0, "America/New_York", date, client=client)


def _client(replies):
    calls = []

    def handler(req):
        calls.append(req)
        return next(replies)
    return httpx.Client(transport=httpx.MockTransport(handler)), calls


def test_one_request_per_location_serves_every_date(monkeypatch):
    ensemble.clear_cache()
    client, calls = _client(iter([httpx.Response(200, json=PAYLOAD)]))
    assert members("2026-10-23", client) == [66.0, 64.0]
    assert members("2026-10-24", client) == [70.0]
    assert len(calls) == 1


def test_rate_limited_fetch_is_retried(monkeypatch):
    ensemble.clear_cache()
    monkeypatch.setattr(http.time, "sleep", lambda s: None)
    client, calls = _client(iter([httpx.Response(429), httpx.Response(200, json=PAYLOAD)]))
    assert members("2026-10-23", client) == [66.0, 64.0]
    assert len(calls) == 2


def test_failure_returns_no_members_and_is_not_cached(monkeypatch):
    ensemble.clear_cache()
    monkeypatch.setattr(http.time, "sleep", lambda s: None)
    client, _ = _client(iter([httpx.Response(500)] * 5 + [httpx.Response(200, json=PAYLOAD)]))
    assert members("2026-10-23", client) == []
    assert members("2026-10-23", client) == [66.0, 64.0]
