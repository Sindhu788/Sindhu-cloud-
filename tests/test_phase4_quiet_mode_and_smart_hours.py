"""Grand Master Batch, Phase 4 Items 5 & 15 -- smart Silent Hours
(high-confidence bypass) and Quiet Mode (manual one-day full mute)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from data_engine import config as base_config
from paper_trading import telegram_bot


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _position(**overrides):
    base = {
        "id": "pos1", "strategy_id": "strat1", "strategy_name": "Test Strategy",
        "symbol": "BTCUSDT", "direction": "long", "entry_price": 100.0,
        "stop_loss": 95.0, "take_profit": 110.0,
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------- Quiet Mode

def test_quiet_mode_starts_off():
    assert telegram_bot.is_quiet_mode_active() is False


def test_set_quiet_mode_activates_it():
    telegram_bot.set_quiet_mode(hours=24)
    assert telegram_bot.is_quiet_mode_active() is True


def test_quiet_mode_expires_after_its_window():
    telegram_bot.set_quiet_mode(hours=1)
    future = datetime.now(timezone.utc) + timedelta(hours=2)
    assert telegram_bot.is_quiet_mode_active(now=future) is False


def test_clear_quiet_mode_turns_it_off_early():
    telegram_bot.set_quiet_mode(hours=24)
    telegram_bot.clear_quiet_mode()
    assert telegram_bot.is_quiet_mode_active() is False


def test_set_quiet_mode_rejects_non_positive_hours():
    with pytest.raises(ValueError):
        telegram_bot.set_quiet_mode(hours=0)


# --------------------------------------------------------------- _effective_silent combination logic

def test_effective_silent_false_by_default():
    assert telegram_bot._effective_silent() is False


def test_effective_silent_true_when_quiet_mode_active_even_with_force_alert():
    telegram_bot.set_quiet_mode(hours=24)
    # Quiet Mode has NO high-confidence exception -- it means everything, on purpose.
    assert telegram_bot._effective_silent(force_alert=True) is True


def test_effective_silent_true_during_silent_hours_without_force_alert():
    telegram_bot.save_settings(silent_hours_enabled=True, silent_hours_start_utc="00:00", silent_hours_end_utc="23:59")
    assert telegram_bot._effective_silent(force_alert=False) is True


def test_effective_silent_bypassed_by_force_alert_during_silent_hours():
    telegram_bot.save_settings(silent_hours_enabled=True, silent_hours_start_utc="00:00", silent_hours_end_utc="23:59")
    assert telegram_bot._effective_silent(force_alert=True) is False


# --------------------------------------------------------------- wired into the real Telegram API call
#
# Goes through _raw_send directly (not the full send_signal_for_position
# pipeline, which has several unrelated real gates -- min TP distance,
# duplicate-signal, confidence, freshness -- that a synthetic test
# position would need to separately satisfy) to verify the ACTUAL
# disable_notification value sent to Telegram's real HTTP API.

def test_high_confidence_signal_bypasses_silent_hours_alert(test_db):
    telegram_bot.save_settings(bot_token="dummy", channel_id="123",
                                silent_hours_enabled=True, silent_hours_start_utc="00:00", silent_hours_end_utc="23:59")
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}
        telegram_bot._raw_send("test message", force_alert=True)
    sent_payload = mock_post.call_args.kwargs["json"]
    assert sent_payload["disable_notification"] is False


def test_regular_signal_stays_silent_during_silent_hours(test_db):
    telegram_bot.save_settings(bot_token="dummy", channel_id="123",
                                silent_hours_enabled=True, silent_hours_start_utc="00:00", silent_hours_end_utc="23:59")
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}
        telegram_bot._raw_send("test message", force_alert=False)
    sent_payload = mock_post.call_args.kwargs["json"]
    assert sent_payload["disable_notification"] is True


def test_public_settings_reports_quiet_mode_state():
    telegram_bot.set_quiet_mode(hours=24)
    s = telegram_bot.public_settings()
    assert s["quiet_mode_active"] is True
    assert s["quiet_mode_until"] is not None
