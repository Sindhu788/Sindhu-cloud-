"""Tests for the Telegram Dashboard's master ON/OFF switch
(paper_trading.telegram_bot._master_enabled / master_send_enabled
setting) -- when OFF, nothing gets sent to Telegram under any
circumstance, regardless of confidence gating, and this must apply to
every real-send path: Manual Override / on-demand send
(send_signal_for_position, used by both trigger_type="manual" and
"automatic") and the close-result follow-up (send_close_followup).
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


@pytest.fixture(autouse=True)
def no_real_live_price(monkeypatch):
    # See test_telegram_dual_tier.py's comment -- fictional entry_price
    # for a real symbol would otherwise trip the real price-drift check.
    monkeypatch.setattr(telegram_bot, "_fetch_live_price", lambda *a, **k: None)


def _open_position(**overrides):
    pos = {
        "id": "pos1", "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        # Fresh timestamp -- see test_telegram_dual_tier.py's comment on
        # why (Signal Freshness Gate, Batch 3 Task 4 Part B).
        "entry_time": int(datetime.now(timezone.utc).timestamp() * 1000),
        "created_at": "2026-01-01T00:00:00+00:00",
        "strategy_id": "strat1", "strategy_name": "Test Strategy",
    }
    pos.update(overrides)
    storage.open_paper_position(pos)
    return pos


def test_master_switch_defaults_to_on():
    assert telegram_bot.public_settings()["master_send_enabled"] is True
    assert telegram_bot._master_enabled() is True


def test_master_switch_persists_across_reload():
    telegram_bot.save_settings(master_send_enabled=False)
    assert telegram_bot.public_settings()["master_send_enabled"] is False
    # Reload settings fresh from disk (simulates a restart reading the
    # same JSON file) -- the switch must still read as OFF.
    assert telegram_bot._master_enabled() is False


def test_send_signal_blocked_when_master_off(test_db):
    telegram_bot.save_settings(bot_token="x", channel_id="y", master_send_enabled=False)
    _open_position()
    with patch.object(telegram_bot, "_raw_send") as mock_send:
        result = telegram_bot.send_signal_for_position("pos1", trigger_type="manual")
    mock_send.assert_not_called()
    assert result["ok"] is False
    assert "master switch" in result["error"]


def test_send_signal_works_when_master_on(test_db):
    telegram_bot.save_settings(bot_token="x", channel_id="y", master_send_enabled=True)
    _open_position()
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        result = telegram_bot.send_signal_for_position("pos1", trigger_type="manual")
    mock_send.assert_called_once()
    assert result["ok"] is True


def test_master_switch_blocks_automatic_trigger_type_too(test_db):
    """The automatic high-confidence rule (A3) also funnels through
    send_signal_for_position() -- confirms the master switch isn't
    bypassable just by using trigger_type='automatic'."""
    telegram_bot.save_settings(bot_token="x", channel_id="y", master_send_enabled=False)
    _open_position()
    with patch.object(telegram_bot, "_raw_send") as mock_send:
        result = telegram_bot.send_signal_for_position("pos1", trigger_type="automatic")
    mock_send.assert_not_called()
    assert result["ok"] is False


def test_master_switch_logs_blocked_attempt_to_audit_trail(test_db):
    telegram_bot.save_settings(bot_token="x", channel_id="y", master_send_enabled=False)
    _open_position()
    telegram_bot.send_signal_for_position("pos1", trigger_type="manual")
    logged = storage.list_telegram_messages(limit=5)
    assert len(logged) == 1
    assert logged[0]["success"] == 0
    assert "master switch" in logged[0]["error"]


def test_close_followup_blocked_when_master_off(test_db):
    telegram_bot.save_settings(bot_token="x", channel_id="y", master_send_enabled=False)
    _open_position()
    storage.log_telegram_message("pos1", "strat1", "Test Strategy", "manual", "text", True, None, "2026-01-01T00:00:00+00:00")
    closed = {"id": "pos1", "symbol": "BTCUSDT", "strategy_id": "strat1", "strategy_name": "Test Strategy",
              "exit_price": 110.0, "exit_reason": "take_profit", "pnl": 10.0, "pnl_pct": 10.0}
    with patch.object(telegram_bot, "_raw_send") as mock_send:
        result = telegram_bot.send_close_followup(closed)
    mock_send.assert_not_called()
    assert result is None


def test_close_followup_works_when_master_on(test_db):
    telegram_bot.save_settings(bot_token="x", channel_id="y", master_send_enabled=True)
    _open_position()
    storage.log_telegram_message("pos1", "strat1", "Test Strategy", "manual", "text", True, None, "2026-01-01T00:00:00+00:00")
    closed = {"id": "pos1", "symbol": "BTCUSDT", "strategy_id": "strat1", "strategy_name": "Test Strategy",
              "exit_price": 110.0, "exit_reason": "take_profit", "pnl": 10.0, "pnl_pct": 10.0}
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        result = telegram_bot.send_close_followup(closed)
    mock_send.assert_called_once()
    assert result["ok"] is True


def test_test_message_is_not_gated_by_master_switch():
    """send_test_message() is a deliberate connectivity check, not a
    signal -- it must keep working even while the master switch is off,
    so the CEO can still verify the bot connection while paused."""
    telegram_bot.save_settings(bot_token="x", channel_id="y", master_send_enabled=False)
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        result = telegram_bot.send_test_message()
    mock_send.assert_called_once()
    assert result["ok"] is True
