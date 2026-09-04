"""Master Task 3, Phase 2.22: trailing-stop-active tag on the signal
message, and a break-even-move Telegram notification -- both purely
informational, no new trading logic.
"""

from unittest.mock import patch

import pytest

from data_engine import config as base_config, storage
from paper_trading import config as pt_config, position_manager, telegram_bot


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _position(**overrides):
    pos = {
        "id": "pos1", "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "stop_loss": 95.0, "take_profit": 120.0, "size": 1.0,
        "strategy_id": "strat1", "strategy_name": "Test Strategy", "entry_time": 1700000000000,
    }
    pos.update(overrides)
    return pos


# --------------------------------------------------------------- trailing-stop tag on the signal message

def test_signal_message_shows_trailing_stop_tag_when_profit_lock_enabled(test_db):
    pt_config.update(profit_lock_enabled=True)
    text = telegram_bot.format_signal_message(_position())
    assert "Trailing Stop Active" in text


def test_signal_message_omits_trailing_stop_tag_when_disabled(test_db):
    pt_config.update(profit_lock_enabled=False)
    text = telegram_bot.format_signal_message(_position())
    assert "Trailing Stop Active" not in text


# --------------------------------------------------------------- break-even notification

def _open_and_log(pos_id="pos1"):
    storage.open_paper_position({
        "id": pos_id, "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0, "stop_loss": 95.0,
        "entry_time": 1700000000000, "created_at": "2026-01-01T00:00:00+00:00",
        "strategy_id": "strat1", "strategy_name": "Test Strategy",
    })
    storage.log_telegram_message(pos_id, "strat1", "Test Strategy", "manual", "text", True, None, "2026-01-01T00:00:00+00:00")


def test_send_breakeven_notification_requires_a_prior_signal(test_db):
    telegram_bot.save_settings(bot_token="x", channel_id="y", master_send_enabled=True)
    storage.open_paper_position({
        "id": "nosig", "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0, "stop_loss": 95.0,
        "entry_time": 1700000000000, "created_at": "2026-01-01T00:00:00+00:00",
        "strategy_id": "strat1", "strategy_name": "Test Strategy",
    })
    result = telegram_bot.send_breakeven_notification(_position(id="nosig"))
    assert result is None


def test_send_breakeven_notification_sends_when_signal_was_sent(test_db):
    telegram_bot.save_settings(bot_token="x", channel_id="y", master_send_enabled=True)
    _open_and_log()
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        result = telegram_bot.send_breakeven_notification(_position(stop_loss=100.0))
    assert result["ok"] is True
    assert "break-even" in mock_send.call_args[0][0].lower()


def test_send_breakeven_notification_respects_master_switch(test_db):
    telegram_bot.save_settings(bot_token="x", channel_id="y", master_send_enabled=False)
    _open_and_log()
    result = telegram_bot.send_breakeven_notification(_position())
    assert result is None


# --------------------------------------------------------------- position_manager wiring: fires exactly once

def test_monitor_and_close_notifies_breakeven_exactly_once(test_db, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(base_config.CONFIG_DIR))
    pt_config.update(profit_lock_enabled=True, profit_lock_trigger_r=1.0, profit_lock_trail_pct=50.0)
    _open_and_log()
    storage.update_position_excursion("pos1", 100.0, 100.0)

    calls = []
    monkeypatch.setattr(telegram_bot, "send_breakeven_notification", lambda pos: calls.append(pos["id"]))

    # First tick: price runs up to 1R+ favorable (entry 100, stop 95, risk=5 -> 1R = 105).
    # highest_price_seen becomes 106 -> trailing stop computes to entry+0.5R=102.5, which is
    # already >= entry (100) -> breakeven-or-better reached for the FIRST time.
    position_manager.monitor_and_close("binance", "BTCUSDT", latest_price=106.0, high=106.0, low=106.0)
    assert calls == ["pos1"]

    # Second tick, price still favorable but no NEW breakeven crossing (already past it) --
    # must not notify again.
    position_manager.monitor_and_close("binance", "BTCUSDT", latest_price=107.0, high=107.0, low=107.0)
    assert calls == ["pos1"]
