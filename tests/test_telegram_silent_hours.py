"""Grand Feature Expansion, Phase 2 Feature 24: Silent Hours / Do-Not-
Disturb. Signals still send and are fully logged during the window --
only Telegram's own disable_notification flag is set, muting the phone
alert without withholding, delaying, or queuing the message at all.
"""

from datetime import datetime, timezone

import pytest

from data_engine import config as base_config
from paper_trading import telegram_bot


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _dt(hour, minute=0):
    return datetime(2026, 1, 1, hour, minute, tzinfo=timezone.utc)


def test_disabled_by_default(test_db):
    assert telegram_bot.is_within_silent_hours(_dt(23, 30)) is False


def test_same_day_window(test_db):
    telegram_bot.save_settings(silent_hours_enabled=True, silent_hours_start_utc="13:00", silent_hours_end_utc="14:00")
    assert telegram_bot.is_within_silent_hours(_dt(13, 30)) is True
    assert telegram_bot.is_within_silent_hours(_dt(12, 59)) is False
    assert telegram_bot.is_within_silent_hours(_dt(14, 0)) is False  # end is exclusive


def test_overnight_window_spanning_midnight(test_db):
    telegram_bot.save_settings(silent_hours_enabled=True, silent_hours_start_utc="23:00", silent_hours_end_utc="07:00")
    assert telegram_bot.is_within_silent_hours(_dt(23, 30)) is True
    assert telegram_bot.is_within_silent_hours(_dt(3, 0)) is True
    assert telegram_bot.is_within_silent_hours(_dt(6, 59)) is True
    assert telegram_bot.is_within_silent_hours(_dt(7, 0)) is False  # end is exclusive
    assert telegram_bot.is_within_silent_hours(_dt(12, 0)) is False


def test_zero_width_window_means_always_off(test_db):
    telegram_bot.save_settings(silent_hours_enabled=True, silent_hours_start_utc="09:00", silent_hours_end_utc="09:00")
    assert telegram_bot.is_within_silent_hours(_dt(9, 0)) is False
    assert telegram_bot.is_within_silent_hours(_dt(15, 0)) is False


def test_malformed_time_strings_fail_safe_to_not_silent(test_db):
    telegram_bot.save_settings(silent_hours_enabled=True, silent_hours_start_utc="not-a-time", silent_hours_end_utc="07:00")
    assert telegram_bot.is_within_silent_hours(_dt(23, 30)) is False


def test_raw_send_sets_disable_notification_during_the_window(test_db, monkeypatch):
    telegram_bot.save_settings(bot_token="dummy", channel_id="123",
                                silent_hours_enabled=True, silent_hours_start_utc="00:00", silent_hours_end_utc="23:59")
    captured = {}

    class _FakeResponse:
        status_code = 200
        def json(self):
            return {"ok": True}

    def _fake_post(url, json, timeout, proxies):
        captured.update(json)
        return _FakeResponse()

    monkeypatch.setattr(telegram_bot.requests, "post", _fake_post)
    telegram_bot._raw_send("hello")
    assert captured["disable_notification"] is True


def test_raw_send_does_not_set_disable_notification_outside_the_window(test_db, monkeypatch):
    telegram_bot.save_settings(bot_token="dummy", channel_id="123", silent_hours_enabled=False)
    captured = {}

    class _FakeResponse:
        status_code = 200
        def json(self):
            return {"ok": True}

    def _fake_post(url, json, timeout, proxies):
        captured.update(json)
        return _FakeResponse()

    monkeypatch.setattr(telegram_bot.requests, "post", _fake_post)
    telegram_bot._raw_send("hello")
    assert captured["disable_notification"] is False


def test_message_still_sends_successfully_during_silent_hours(test_db, monkeypatch):
    """The core promise of this feature: nothing is withheld, delayed, or
    queued -- only muted."""
    telegram_bot.save_settings(bot_token="dummy", channel_id="123",
                                silent_hours_enabled=True, silent_hours_start_utc="00:00", silent_hours_end_utc="23:59")

    class _FakeResponse:
        status_code = 200
        def json(self):
            return {"ok": True}

    monkeypatch.setattr(telegram_bot.requests, "post", lambda *a, **k: _FakeResponse())
    ok, err = telegram_bot._raw_send("hello")
    assert ok is True
    assert err is None
