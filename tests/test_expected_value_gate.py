"""Grand Master Batch #2, Phase 1.4: real evidence for the Expected-Value
Gate -- only send a signal if this exact strategy's own REAL, already-
closed paper trades show a genuinely positive average dollar result. An
ADDITIONAL filter on top of (never a replacement for) the Confluence/
Wilson/Freshness/TP-distance/Duplicate/Confidence gates -- see
paper_trading.telegram_bot.expected_value_check's own docstring for why
this is built on real paper-trading history rather than the backtest
engine's local-filesystem-only walk-forward result.
"""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from data_engine import config as base_config, storage
from paper_trading import telegram_bot


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _closed_trade(i, pnl, strategy_id="strat1"):
    pos_id = f"closed{i}"
    storage.open_paper_position({
        "id": pos_id, "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": 1700000000000 + i, "created_at": "2026-01-01T00:00:00+00:00",
        "strategy_id": strategy_id, "strategy_name": "Test Strategy",
    })
    storage.close_paper_position(
        pos_id, exit_price=100.0 + pnl, exit_time=1700000000000 + i, pnl=pnl, pnl_pct=pnl / 100.0 * 100,
        exit_reason="take_profit", lifecycle={}, reflection={}, closed_at="2026-01-02T00:00:00+00:00",
    )


def _open_position(strategy_id="strat1", **overrides):
    pos = {
        "id": "posX", "exchange": "binance", "symbol": "ETHUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": int(datetime.now(timezone.utc).timestamp() * 1000),
        "created_at": "2026-01-01T00:00:00+00:00",
        "strategy_id": strategy_id, "strategy_name": "Test Strategy", "stop_loss": 90.0, "take_profit": 130.0,
        "market_state": "trending_up", "session": "london", "entry_reason": "test",
    }
    pos.update(overrides)
    storage.open_paper_position(pos)
    return pos


def test_passes_open_with_no_strategy_id(test_db):
    ok, reason = telegram_bot.expected_value_check({"strategy_id": None})
    assert ok is True and reason is None


def test_passes_open_below_minimum_sample_even_if_all_losing(test_db):
    for i in range(telegram_bot.EV_GATE_MIN_TRADES - 1):
        _closed_trade(i, pnl=-10.0)
    ok, reason = telegram_bot.expected_value_check({"strategy_id": "strat1"})
    assert ok is True and reason is None


def test_blocks_once_minimum_sample_reached_with_real_negative_expectancy(test_db):
    # 25 real closed trades, genuinely negative average ($-2/trade: 15
    # losers at -10, 10 winners at +5.5 -> total = -150+55 = -95, /25 = -3.8)
    for i in range(15):
        _closed_trade(i, pnl=-10.0)
    for i in range(15, 25):
        _closed_trade(i, pnl=5.5)
    ok, reason = telegram_bot.expected_value_check({"strategy_id": "strat1"})
    assert ok is False
    assert "-3.8" in reason or "$-3.80" in reason or "expectancy" in reason
    assert "25 closed trades" in reason


def test_passes_once_minimum_sample_reached_with_real_positive_expectancy(test_db):
    for i in range(10):
        _closed_trade(i, pnl=-5.0)
    for i in range(10, 25):
        _closed_trade(i, pnl=10.0)
    ok, reason = telegram_bot.expected_value_check({"strategy_id": "strat1"})
    assert ok is True and reason is None


def test_gate_is_scoped_per_strategy_not_global(test_db):
    for i in range(30):
        _closed_trade(i, pnl=-10.0, strategy_id="losing_strategy")
    for i in range(30, 60):
        _closed_trade(i, pnl=10.0, strategy_id="winning_strategy")
    ok_losing, _ = telegram_bot.expected_value_check({"strategy_id": "losing_strategy"})
    ok_winning, _ = telegram_bot.expected_value_check({"strategy_id": "winning_strategy"})
    assert ok_losing is False
    assert ok_winning is True


def test_wired_into_send_signal_for_position_blocks_a_real_send(test_db, monkeypatch):
    for i in range(15):
        _closed_trade(i, pnl=-10.0)
    for i in range(15, 25):
        _closed_trade(i, pnl=5.5)
    _open_position(strategy_id="strat1")
    telegram_bot.save_settings(bot_token="x", channel_id="y", master_send_enabled=True)
    monkeypatch.setattr(telegram_bot, "_fetch_live_price", lambda *a, **k: None)
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        result = telegram_bot.send_signal_for_position("posX", trigger_type="manual")
    mock_send.assert_not_called()
    assert result["ok"] is False
    assert "expectancy" in result["error"]


def test_wired_into_send_signal_for_position_still_sends_a_real_good_strategy(test_db, monkeypatch):
    for i in range(10):
        _closed_trade(i, pnl=-5.0)
    for i in range(10, 25):
        _closed_trade(i, pnl=10.0)
    _open_position(strategy_id="strat1")
    telegram_bot.save_settings(bot_token="x", channel_id="y", master_send_enabled=True)
    monkeypatch.setattr(telegram_bot, "_fetch_live_price", lambda *a, **k: None)
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        result = telegram_bot.send_signal_for_position("posX", trigger_type="manual")
    mock_send.assert_called_once()
    assert result["ok"] is True
