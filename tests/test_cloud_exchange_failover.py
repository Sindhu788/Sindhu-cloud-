"""Urgent bug fix, 2026-09-08: bybit (the cloud fallback picked by the
2026-09-07 Binance-451 fix) started 403-ing every request from Render's
servers too ("The Amazon CloudFront distribution is configured to block
access from your country") -- confirmed live, 100% of ticks failing for
3+ hours straight with zero trades ever evaluated. Hardcoding a single
"currently safe" exchange has now broken this project twice, so the real
fix is a runtime failover across every enabled exchange instead of a
second hardcoded guess.
"""
from unittest.mock import MagicMock

import pytest

from data_engine.exchanges import registry
from data_engine.symbols import pick_top_symbols


@pytest.fixture(autouse=True)
def _reset_last_good():
    registry._last_good_exchange["id"] = None
    yield
    registry._last_good_exchange["id"] = None


def _make_client(tradeable=None, ohlcv=None, fail=False, fail_ohlcv=False):
    client = MagicMock()
    if fail:
        client.get_tradeable_symbols.side_effect = RuntimeError("geo-blocked")
    else:
        client.get_tradeable_symbols.return_value = tradeable or {"BTC": "BTC/USDT"}
    if fail_ohlcv:
        client.get_ohlcv.side_effect = RuntimeError("geo-blocked on candles")
    else:
        client.get_ohlcv.return_value = ohlcv if ohlcv is not None else [(1, 2, 3, 4, 5, 6, 7, 8, 9)]
    return client


def test_falls_through_to_next_candidate_when_first_fails(monkeypatch):
    bad = _make_client(fail=True)
    good = _make_client()
    monkeypatch.setattr(registry, "get_exchange_client",
                         lambda eid: {"bybit": bad, "okx": good}[eid])

    exchange_id, client, tradeable = registry.get_working_exchange_client(["bybit", "okx"], "USDT")

    assert exchange_id == "okx"
    assert client is good
    assert tradeable == {"BTC": "BTC/USDT"}


def test_empty_ohlcv_probe_counts_as_failure(monkeypatch):
    """get_tradeable_symbols succeeding isn't enough -- an exchange that
    answers the instruments call but geo-blocks candle fetches must still
    be skipped (this is exactly why the health check probes get_ohlcv
    too, not just get_tradeable_symbols)."""
    bad = _make_client(fail_ohlcv=True)
    good = _make_client()
    monkeypatch.setattr(registry, "get_exchange_client",
                         lambda eid: {"bybit": bad, "okx": good}[eid])

    exchange_id, client, tradeable = registry.get_working_exchange_client(["bybit", "okx"], "USDT")

    assert exchange_id == "okx"


def test_remembers_last_good_and_tries_it_first(monkeypatch):
    calls = []

    def fake_get_exchange_client(eid):
        calls.append(eid)
        return {"bybit": _make_client(fail=True), "okx": _make_client()}[eid]

    monkeypatch.setattr(registry, "get_exchange_client", fake_get_exchange_client)

    registry.get_working_exchange_client(["bybit", "okx"], "USDT")
    assert registry.last_known_working_exchange() == "okx"

    calls.clear()
    good_okx = _make_client()

    def fake_get_exchange_client2(eid):
        calls.append(eid)
        return good_okx

    monkeypatch.setattr(registry, "get_exchange_client", fake_get_exchange_client2)
    registry.get_working_exchange_client(["bybit", "okx"], "USDT")
    # okx (the last-known-good) must be tried FIRST this time, not bybit.
    assert calls[0] == "okx"


def test_all_candidates_failing_raises_with_every_reason(monkeypatch):
    monkeypatch.setattr(registry, "get_exchange_client",
                         lambda eid: _make_client(fail=True))

    with pytest.raises(RuntimeError) as exc_info:
        registry.get_working_exchange_client(["bybit", "okx"], "USDT")

    assert "bybit" in str(exc_info.value)
    assert "okx" in str(exc_info.value)


def test_pick_top_symbols_accepts_prefetched_tradeable(monkeypatch):
    """When the failover already fetched tradeable symbols as part of its
    own health check, pick_top_symbols must not call get_tradeable_symbols
    on the client a second time."""
    client = MagicMock()
    client.get_tradeable_symbols.side_effect = AssertionError("should not be called again")
    monkeypatch.setattr(
        "data_engine.symbols.get_top_market_cap_coins",
        lambda limit: [{"symbol": "btc"}],
    )

    result = pick_top_symbols(client, n=1, quote="USDT", tradeable={"BTC": "BTC/USDT"})

    assert result == ["BTC/USDT"]
    client.get_tradeable_symbols.assert_not_called()
