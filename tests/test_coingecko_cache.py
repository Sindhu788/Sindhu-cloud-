"""Urgent bug fix, 2026-09-08 (continued from the exchange-failover fix):
once ticks actually reached CoinGecko (past the fixed exchange geo-block),
every single tick started hitting CoinGecko's own 429 rate limit instead --
confirmed live. get_top_market_cap_coins() now caches its result for
_CACHE_TTL_SECONDS and retries a 429 with backoff before falling back to a
stale cache (or raising, if there is no cache to fall back to).
"""
from unittest.mock import MagicMock

import pytest
import requests

from data_engine import coingecko_client as cg


@pytest.fixture(autouse=True)
def _reset_cache():
    cg._cache["limit"] = None
    cg._cache["coins"] = None
    cg._cache["fetched_at"] = 0.0
    yield
    cg._cache["limit"] = None
    cg._cache["coins"] = None
    cg._cache["fetched_at"] = 0.0


def _ok_response(coins):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = coins
    resp.raise_for_status.return_value = None
    return resp


def _empty_response():
    return _ok_response([])


def _rate_limited_response():
    resp = MagicMock()
    resp.status_code = 429
    resp.headers = {}
    resp.url = "https://api.coingecko.com/api/v3/coins/markets"
    return resp


def test_second_call_within_ttl_never_hits_network_again(monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(params["page"])
        if params["page"] == 1:
            return _ok_response([{"symbol": "btc"}] * 100)
        return _empty_response()

    monkeypatch.setattr(cg._session, "get", fake_get)
    monkeypatch.setattr(cg.time, "sleep", lambda s: None)

    first = cg.get_top_market_cap_coins(limit=50)
    calls_after_first = list(calls)
    second = cg.get_top_market_cap_coins(limit=50)

    assert len(first) == 50
    assert second == first
    assert calls == calls_after_first  # no new network calls on the second call


def test_cache_expires_after_ttl(monkeypatch):
    fake_now = [1000.0]
    monkeypatch.setattr(cg.time, "monotonic", lambda: fake_now[0])
    monkeypatch.setattr(cg.time, "sleep", lambda s: None)
    call_count = [0]

    def fake_get(url, params=None, timeout=None):
        if params["page"] == 1:
            call_count[0] += 1
            return _ok_response([{"symbol": "btc"}] * 100)
        return _empty_response()

    monkeypatch.setattr(cg._session, "get", fake_get)

    cg.get_top_market_cap_coins(limit=50)
    assert call_count[0] == 1

    fake_now[0] += cg._CACHE_TTL_SECONDS + 1
    cg.get_top_market_cap_coins(limit=50)
    assert call_count[0] == 2


def test_429_retries_with_backoff_then_succeeds(monkeypatch):
    monkeypatch.setattr(cg.time, "sleep", lambda s: None)
    attempts = {"n": 0}

    def fake_get(url, params=None, timeout=None):
        if params["page"] == 1:
            attempts["n"] += 1
            if attempts["n"] < 3:
                return _rate_limited_response()
            return _ok_response([{"symbol": "btc"}] * 100)
        return _empty_response()

    monkeypatch.setattr(cg._session, "get", fake_get)

    coins = cg.get_top_market_cap_coins(limit=50)
    assert len(coins) == 50
    assert attempts["n"] == 3


def test_429_falls_back_to_stale_cache_when_available(monkeypatch):
    monkeypatch.setattr(cg.time, "sleep", lambda s: None)
    fake_now = [1000.0]
    monkeypatch.setattr(cg.time, "monotonic", lambda: fake_now[0])

    def fake_get_ok(url, params=None, timeout=None):
        if params["page"] == 1:
            return _ok_response([{"symbol": "btc"}] * 100)
        return _empty_response()

    monkeypatch.setattr(cg._session, "get", fake_get_ok)
    first = cg.get_top_market_cap_coins(limit=50)

    fake_now[0] += cg._CACHE_TTL_SECONDS + 1
    monkeypatch.setattr(cg._session, "get", lambda *a, **k: _rate_limited_response())

    second = cg.get_top_market_cap_coins(limit=50)
    assert second == first


def test_429_with_no_cache_raises(monkeypatch):
    monkeypatch.setattr(cg.time, "sleep", lambda s: None)
    monkeypatch.setattr(cg._session, "get", lambda *a, **k: _rate_limited_response())

    with pytest.raises(requests.HTTPError):
        cg.get_top_market_cap_coins(limit=50)
