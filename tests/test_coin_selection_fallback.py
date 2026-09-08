"""Urgent bug fix, 2026-09-08: confirmed live that CoinGecko's free tier
sustains 429 (Too Many Requests) from Render's shared IP for 40+ minutes
straight with zero successful calls -- caching alone (data_engine.
coingecko_client) cannot help when there's never been one successful call
to cache. data_engine.symbols.pick_top_symbols() now falls back to
ranking by the exchange's own real 24h quote volume instead of leaving
every tick permanently stuck with zero symbols.
"""
from unittest.mock import MagicMock

from data_engine import symbols


def _client(tradeable, tickers=None, tickers_raise=False):
    client = MagicMock()
    client.get_tradeable_symbols.return_value = tradeable
    if tickers_raise:
        client.get_tickers.side_effect = RuntimeError("exchange unreachable")
    else:
        client.get_tickers.return_value = tickers or {}
    return client


def test_falls_back_to_exchange_volume_when_coingecko_fails(monkeypatch):
    monkeypatch.setattr(symbols, "get_top_market_cap_coins",
                         lambda limit: (_ for _ in ()).throw(RuntimeError("429 rate limited")))
    tradeable = {"BTC": "BTC/USDT", "ETH": "ETH/USDT", "XRP": "XRP/USDT"}
    tickers = {
        "BTC/USDT": {"volume": 500.0},
        "ETH/USDT": {"volume": 900.0},
        "XRP/USDT": {"volume": 100.0},
    }
    client = _client(tradeable, tickers)

    result = symbols.pick_top_symbols(client, n=2, quote="USDT", tradeable=tradeable)

    assert result == ["ETH/USDT", "BTC/USDT"]  # ranked by volume desc, capped at n=2


def test_fallback_excludes_symbols_with_no_ticker_data(monkeypatch):
    monkeypatch.setattr(symbols, "get_top_market_cap_coins",
                         lambda limit: (_ for _ in ()).throw(RuntimeError("429 rate limited")))
    tradeable = {"BTC": "BTC/USDT", "ETH": "ETH/USDT"}
    tickers = {"BTC/USDT": {"volume": 500.0}}  # ETH/USDT missing entirely
    client = _client(tradeable, tickers)

    result = symbols.pick_top_symbols(client, n=10, quote="USDT", tradeable=tradeable)

    assert result == ["BTC/USDT"]


def test_fallback_returns_empty_when_exchange_tickers_also_fail(monkeypatch):
    monkeypatch.setattr(symbols, "get_top_market_cap_coins",
                         lambda limit: (_ for _ in ()).throw(RuntimeError("429 rate limited")))
    tradeable = {"BTC": "BTC/USDT"}
    client = _client(tradeable, tickers_raise=True)

    result = symbols.pick_top_symbols(client, n=10, quote="USDT", tradeable=tradeable)

    assert result == []


def test_normal_coingecko_success_path_is_unaffected(monkeypatch):
    monkeypatch.setattr(symbols, "get_top_market_cap_coins",
                         lambda limit: [{"symbol": "btc"}, {"symbol": "eth"}])
    tradeable = {"BTC": "BTC/USDT", "ETH": "ETH/USDT"}
    client = _client(tradeable)

    result = symbols.pick_top_symbols(client, n=2, quote="USDT", tradeable=tradeable)

    assert result == ["BTC/USDT", "ETH/USDT"]
    client.get_tickers.assert_not_called()
