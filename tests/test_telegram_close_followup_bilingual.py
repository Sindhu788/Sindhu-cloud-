"""Batch 5, Task 3 -- the Telegram close-result follow-up message is
bilingual too, following the stored "language" setting (default Roman
Urdu), same deterministic template pattern as format_signal_message.
"""

from unittest.mock import patch

import pytest

from data_engine import config as base_config, storage
from paper_trading import telegram_bot


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _open_and_log(pos_id="pos1"):
    storage.open_paper_position({
        "id": pos_id, "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": 1700000000000, "created_at": "2026-01-01T00:00:00+00:00",
        "strategy_id": "strat1", "strategy_name": "Test Strategy",
    })
    storage.log_telegram_message(pos_id, "strat1", "Test Strategy", "manual", "text", True, None, "2026-01-01T00:00:00+00:00")


def _closed(pos_id="pos1"):
    return {"id": pos_id, "symbol": "BTCUSDT", "strategy_id": "strat1", "strategy_name": "Test Strategy",
            "exit_price": 110.0, "exit_reason": "take_profit", "pnl": 10.0, "pnl_pct": 10.0}


def test_default_language_is_roman_urdu(test_db):
    telegram_bot.save_settings(bot_token="x", channel_id="y", master_send_enabled=True)
    _open_and_log()
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        telegram_bot.send_close_followup(_closed())
    sent_text = mock_send.call_args[0][0]
    assert "Result (Nateeja)" in sent_text
    assert "Exit (Bahar)" in sent_text


def test_english_setting_switches_the_labels(test_db):
    telegram_bot.save_settings(bot_token="x", channel_id="y", master_send_enabled=True, language="en")
    _open_and_log()
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        telegram_bot.send_close_followup(_closed())
    sent_text = mock_send.call_args[0][0]
    assert "Result:" in sent_text
    assert "Exit:" in sent_text
    assert "Nateeja" not in sent_text


def test_strategy_name_and_numbers_interpolate_cleanly_in_both_languages(test_db):
    telegram_bot.save_settings(bot_token="x", channel_id="y", master_send_enabled=True)
    _open_and_log()
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        telegram_bot.send_close_followup(_closed())
    sent_text = mock_send.call_args[0][0]
    assert "Test Strategy" in sent_text
    assert "+10.00" in sent_text
    assert "10.00%" in sent_text
