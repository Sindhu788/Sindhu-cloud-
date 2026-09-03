"""Grand Feature Expansion, Phase 5 Feature 15: Backtest Replay Visualizer
(GET /api/backtesting/replay/{batch_id}/{symbol}) -- a full-run, bar-by-bar
replay, distinct from the existing Trade Audit (one static candle window
per SELECTED trade) and the desktop dashboard's own TradeReplayDialog
(also per-trade snapshots, PySide6, not this web app).
"""

import pandas as pd
import pytest
from fastapi import HTTPException

from data_engine import storage
from sindhu_web.api import backtesting as backtesting_api


def _fake_df(n):
    idx = pd.date_range("2026-01-01", periods=n, freq="h")
    return pd.DataFrame({
        "open": [100.0 + i for i in range(n)], "high": [101.0 + i for i in range(n)],
        "low": [99.0 + i for i in range(n)], "close": [100.5 + i for i in range(n)],
    }, index=idx)


def _seed_batch(test_db, batch_id="batch1", symbol="BTCUSDT", timeframe="1h", n_trades=2):
    storage.create_batch(batch_id, "Test Strategy", "binance",
                          {"initial_balance": 10000.0, "symbols": [symbol], "start_ms": 0, "end_ms": 1000},
                          "2026-01-01T00:00:00+00:00")
    trades = [
        {"trade_num": i, "side": "long", "entry_time": i * 1000, "entry_price": 100.0, "size": 1.0}
        for i in range(n_trades)
    ]
    storage.save_trades(batch_id, symbol, timeframe, trades)


def test_404_for_unknown_batch(test_db):
    with pytest.raises(HTTPException) as exc_info:
        backtesting_api.get_backtest_replay("does-not-exist", "BTCUSDT")
    assert exc_info.value.status_code == 404


def test_404_when_symbol_has_no_trades(test_db):
    _seed_batch(test_db)
    with pytest.raises(HTTPException) as exc_info:
        backtesting_api.get_backtest_replay("batch1", "ETHUSDT")
    assert exc_info.value.status_code == 404


def test_returns_candles_and_trades(test_db, monkeypatch):
    _seed_batch(test_db)
    monkeypatch.setattr(backtesting_api, "get_ohlcv", lambda *a, **k: _fake_df(10))
    result = backtesting_api.get_backtest_replay("batch1", "BTCUSDT")
    assert result["symbol"] == "BTCUSDT"
    assert result["timeframe"] == "1h"
    assert len(result["candles"]) == 10
    assert len(result["trades"]) == 2
    assert result["truncated"] is False


def test_truncates_to_max_replay_bars(test_db, monkeypatch):
    _seed_batch(test_db)
    monkeypatch.setattr(backtesting_api, "get_ohlcv",
                         lambda *a, **k: _fake_df(backtesting_api.MAX_REPLAY_BARS + 500))
    result = backtesting_api.get_backtest_replay("batch1", "BTCUSDT")
    assert len(result["candles"]) == backtesting_api.MAX_REPLAY_BARS
    assert result["truncated"] is True


def test_candles_keep_the_most_recent_bars_when_truncated(test_db, monkeypatch):
    _seed_batch(test_db)
    n = backtesting_api.MAX_REPLAY_BARS + 10
    monkeypatch.setattr(backtesting_api, "get_ohlcv", lambda *a, **k: _fake_df(n))
    result = backtesting_api.get_backtest_replay("batch1", "BTCUSDT")
    # The fake df's `open` column increases monotonically with time, so the
    # LAST bar overall should still be present (most-recent-bars kept).
    assert result["candles"][-1]["open"] == pytest.approx(100.0 + (n - 1))
