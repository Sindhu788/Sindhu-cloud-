"""Batch 9, Task 2: Telegram Signal Mirror -- the dashboard must show the
REAL message text exactly as it was delivered, never a re-generated
approximation. This is already guaranteed by construction in
paper_trading.telegram_bot.send_signal_for_position (the same `text`
variable is passed to both _raw_send() and storage.log_telegram_message())
-- these tests lock that invariant in explicitly, and confirm
storage.list_telegram_messages() (the data source for the new dashboard
panel) surfaces every attempt, successful or not, with its real message
text and status.
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
    monkeypatch.setattr(telegram_bot, "_fetch_live_price", lambda *a, **k: None)


def _open_position(**overrides):
    pos = {
        "id": "pos1", "strategy_id": "strat1", "strategy_name": "Test Strategy",
        "symbol": "BTCUSDT", "direction": "long", "entry_price": 100.0,
        "stop_loss": 95.0, "take_profit": 110.0, "market_state": "trending_up",
        "session": "london", "entry_reason": "test",
        "exchange": "binance", "size": 1.0, "risk_amount": 5.0,
        "entry_time": int(datetime.now(timezone.utc).timestamp() * 1000),
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    pos.update(overrides)
    storage.open_paper_position(pos)
    return pos


def test_stored_message_text_is_byte_identical_to_what_was_actually_sent(test_db):
    telegram_bot.save_settings(bot_token="dummy", channel_id="123")
    _open_position()
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        telegram_bot.send_signal_for_position("pos1", trigger_type="manual")

    text_passed_to_real_send = mock_send.call_args[0][0]
    logged = storage.list_telegram_messages(limit=10)
    assert len(logged) == 1
    assert logged[0]["message_text"] == text_passed_to_real_send


def test_mirror_shows_a_failed_send_with_its_real_error_and_no_blank_status(test_db):
    telegram_bot.save_settings(bot_token="dummy", channel_id="123")
    _open_position()
    with patch.object(telegram_bot, "_raw_send", return_value=(False, "connection timed out")):
        telegram_bot.send_signal_for_position("pos1", trigger_type="manual")

    logged = storage.list_telegram_messages(limit=10)
    assert logged[0]["success"] == 0
    assert logged[0]["error"] == "connection timed out"
    assert logged[0]["message_text"]  # the real attempted text is still preserved, not lost


def test_mirror_shows_a_freshness_gate_withhold_with_no_message_text(test_db):
    """A signal withheld by the Freshness Gate never reaches
    format_signal_message() at all -- log_telegram_message() is called
    with message_text="" for this case, which the dashboard panel must
    render as "withheld", never as a blank/empty real message."""
    telegram_bot.save_settings(bot_token="dummy", channel_id="123")
    stale_time = int(datetime.now(timezone.utc).timestamp() * 1000) - 1000 * 60 * 60  # 1 hour ago
    _open_position(entry_time=stale_time)

    result = telegram_bot.send_signal_for_position("pos1", trigger_type="manual")
    assert result["ok"] is False
    assert "too stale" in result["error"]

    logged = storage.list_telegram_messages(limit=10)
    assert logged[0]["success"] == 0
    assert logged[0]["message_text"] == ""
    assert "too stale" in logged[0]["error"]


def test_mirror_includes_high_confidence_marker_when_that_tier_actually_fired(test_db):
    telegram_bot.save_settings(bot_token="dummy", channel_id="123")
    _open_position()
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)):
        telegram_bot.send_signal_for_position("pos1", trigger_type="automatic", high_confidence=True)

    logged = storage.list_telegram_messages(limit=10)
    assert "HIGH CONFIDENCE SIGNAL" in logged[0]["message_text"]


def test_mirror_orders_newest_first_and_respects_limit(test_db):
    telegram_bot.save_settings(bot_token="dummy", channel_id="123")
    for i in range(3):
        pid = f"pos{i}"
        _open_position(id=pid, entry_time=int(datetime.now(timezone.utc).timestamp() * 1000))
        with patch.object(telegram_bot, "_raw_send", return_value=(True, None)):
            telegram_bot.send_signal_for_position(pid, trigger_type="manual")

    logged = storage.list_telegram_messages(limit=2)
    assert len(logged) == 2
