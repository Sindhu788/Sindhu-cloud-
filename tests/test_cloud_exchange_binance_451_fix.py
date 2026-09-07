"""Urgent bug fix, 2026-09-07: api.binance.com returns HTTP 451
(regulatory geo-block) to Render's servers -- confirmed live. Cloud mode
now defaults to "bybit" instead of "binance"; local development is
unaffected. Also fixes a real, separate bug in CCXTClient.get_tickers()
found while switching to bybit: fetch_tickers() with no symbols argument
returns PERPETUAL futures keys on bybit (e.g. "BTC/USDT:USDT"), not spot
("BTC/USDT"), so the old naive suffix filter silently returned zero
tickers -- exactly the shape of bug that shows up as an empty/loading
dashboard.
"""
from unittest.mock import MagicMock

import pytest

from data_engine import config as base_config
from data_engine.exchanges.ccxt_client import CCXTClient


def test_cloud_mode_defaults_to_bybit_not_binance(monkeypatch):
    monkeypatch.setenv("SINDHU_CLOUD_MODE", "1")
    import importlib
    reloaded = importlib.reload(base_config)
    try:
        assert reloaded.DEFAULT_EXCHANGE == "bybit"
    finally:
        monkeypatch.delenv("SINDHU_CLOUD_MODE", raising=False)
        importlib.reload(base_config)


def test_local_mode_still_defaults_to_binance(monkeypatch):
    monkeypatch.delenv("SINDHU_CLOUD_MODE", raising=False)
    import importlib
    reloaded = importlib.reload(base_config)
    assert reloaded.DEFAULT_EXCHANGE == "binance"


def test_paper_trading_engine_default_exchange_respects_cloud_mode(monkeypatch):
    from paper_trading import engine
    monkeypatch.setenv("SINDHU_CLOUD_MODE", "1")
    monkeypatch.setattr(engine.base_config, "load_or_seed",
                         lambda *a, **k: {"default": "binance", "enabled": ["binance", "bybit"]})
    assert engine._default_exchange() == "bybit"


def test_get_tickers_filters_to_real_spot_symbols_only():
    """Real bug reproduction: a mocked exchange whose fetch_tickers()
    returns BOTH a perpetual-style key and a real spot key -- only the
    real spot one (present in .markets as spot=True) must come back."""
    client = CCXTClient.__new__(CCXTClient)
    client.id = "bybit"
    client._markets_loaded = True
    fake_exchange = MagicMock()
    fake_exchange.markets = {
        "BTC/USDT": {"symbol": "BTC/USDT", "spot": True, "quote": "USDT", "active": True},
        "BTC/USDT:USDT": {"symbol": "BTC/USDT:USDT", "spot": False, "quote": "USDT", "active": True},
    }
    fake_exchange.fetch_tickers.return_value = {
        "BTC/USDT": {"last": 79445.6, "percentage": -0.5, "quoteVolume": 324098897.6},
    }
    client._exchange = fake_exchange

    result = client.get_tickers("USDT")

    assert "BTC/USDT" in result
    assert result["BTC/USDT"]["price"] == 79445.6
    fake_exchange.fetch_tickers.assert_called_once_with(["BTC/USDT"])


def test_get_tickers_returns_empty_dict_when_no_spot_markets_for_quote():
    client = CCXTClient.__new__(CCXTClient)
    client.id = "bybit"
    client._markets_loaded = True
    fake_exchange = MagicMock()
    fake_exchange.markets = {"BTC/EUR": {"symbol": "BTC/EUR", "spot": True, "quote": "EUR", "active": True}}
    client._exchange = fake_exchange

    result = client.get_tickers("USDT")

    assert result == {}
    fake_exchange.fetch_tickers.assert_not_called()
