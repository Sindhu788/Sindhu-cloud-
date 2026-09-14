"""Batch 5, Task 3 originally covered the Telegram close-result follow-up
message's bilingual formatting. 2026-09-14: send_close_followup() was
disabled entirely by explicit CEO instruction -- these WIN/LOSS result
notifications were flooding the Telegram channel and crowding out actual
entry signals (see its own docstring in paper_trading/telegram_bot.py).
There is no message left to format, so this file now just guards that the
function stays a true no-op regardless of language/settings, replacing the
old formatting-content assertions.
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


@pytest.mark.parametrize("language", ["ur", "en"])
def test_close_followup_never_sends_regardless_of_language(test_db, language):
    telegram_bot.save_settings(bot_token="x", channel_id="y", master_send_enabled=True, language=language)
    _open_and_log()
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        result = telegram_bot.send_close_followup(_closed())
    mock_send.assert_not_called()
    assert result is None
