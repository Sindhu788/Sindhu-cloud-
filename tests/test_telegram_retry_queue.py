"""Grand Feature Expansion, Phase 2 Feature 11: Delivery Retry Queue.
telegram_bot._raw_send() already retries a handful of times WITHIN one
call for a connection-level failure; this is the separate, longer-horizon
mechanism for when that whole call still failed (Telegram down for
several minutes, a laptop's internet dropping) -- rather than the signal
being lost, it's queued and retried again later by
sweep_pending_telegram_retries(), until it either succeeds or exhausts
MAX_RETRY_ATTEMPTS (at which point it's marked abandoned with a visible
dashboard alert, never retried forever).
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


def _configure():
    telegram_bot.save_settings(bot_token="dummy", channel_id="123")


def test_a_transient_network_failure_gets_queued(test_db):
    _open_position()
    _configure()
    with patch.object(telegram_bot, "_raw_send", return_value=(False, "failed after 3 attempts: ConnectionError()")):
        result = telegram_bot.send_signal_for_position("pos1", trigger_type="manual")

    assert result["ok"] is False
    queue = storage.list_telegram_retry_queue()
    assert len(queue) == 1
    assert queue[0]["position_id"] == "pos1"
    assert queue[0]["status"] == "pending"


def test_a_real_telegram_api_error_is_not_queued(test_db):
    """_raw_send's own docstring: a real API response (bad chat_id, etc)
    is never retried -- retrying would just get the same answer again."""
    _open_position()
    _configure()
    with patch.object(telegram_bot, "_raw_send", return_value=(False, "Bad Request: chat not found")):
        telegram_bot.send_signal_for_position("pos1", trigger_type="manual")

    assert storage.list_telegram_retry_queue() == []


def test_a_successful_send_never_gets_queued(test_db):
    _open_position()
    _configure()
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)):
        result = telegram_bot.send_signal_for_position("pos1", trigger_type="manual")

    assert result["ok"] is True
    assert storage.list_telegram_retry_queue() == []


def test_sweep_delivers_a_queued_retry_that_now_succeeds(test_db):
    _open_position()
    _configure()
    with patch.object(telegram_bot, "_raw_send", return_value=(False, "failed after 3 attempts: x")):
        telegram_bot.send_signal_for_position("pos1", trigger_type="manual")
    assert storage.list_telegram_retry_queue()[0]["status"] == "pending"

    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)):
        result = telegram_bot.sweep_pending_telegram_retries()

    assert result["delivered"] == ["pos1"]
    assert storage.list_telegram_retry_queue()[0]["status"] == "delivered"


def test_sweep_retry_failure_does_not_create_a_second_queue_row(test_db):
    _open_position()
    _configure()
    with patch.object(telegram_bot, "_raw_send", return_value=(False, "failed after 3 attempts: x")):
        telegram_bot.send_signal_for_position("pos1", trigger_type="manual")
        result = telegram_bot.sweep_pending_telegram_retries()

    assert result["still_pending"] == ["pos1"]
    queue = storage.list_telegram_retry_queue()
    assert len(queue) == 1
    assert queue[0]["attempts"] == 1


def test_row_is_abandoned_after_max_attempts_and_raises_an_alert(test_db):
    _open_position()
    _configure()
    with patch.object(telegram_bot, "_raw_send", return_value=(False, "failed after 3 attempts: x")):
        telegram_bot.send_signal_for_position("pos1", trigger_type="manual")
        for _ in range(telegram_bot.MAX_RETRY_ATTEMPTS):
            result = telegram_bot.sweep_pending_telegram_retries()

    assert result["abandoned"] == ["pos1"]
    queue = storage.list_telegram_retry_queue()
    assert queue[0]["status"] == "abandoned"
    assert queue[0]["attempts"] == telegram_bot.MAX_RETRY_ATTEMPTS

    alerts = storage.list_paper_alerts()
    match = next(a for a in alerts if a["alert_type"] == "telegram_delivery_abandoned")
    assert "pos1" in match["message"]
    assert match["strategy_id"] == "strat1"


def test_sweep_with_an_empty_queue_is_a_safe_no_op(test_db):
    result = telegram_bot.sweep_pending_telegram_retries()
    assert result == {"delivered": [], "abandoned": [], "still_pending": []}
