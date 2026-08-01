"""Batch 2, Task 3 -- dashboard alert for an extended Telegram signal
drought: 24+ hours with zero signals sent (any tier), auto-clearing the
moment a new signal actually sends (computed fresh from the real
last-sent timestamp every call, nothing to separately reset).
"""

from datetime import datetime, timedelta, timezone

from data_engine import storage
from paper_trading import telegram_bot


def _iso(dt):
    return dt.isoformat()


def _log(trigger_type, success, sent_at, position_id="pos1"):
    storage.log_telegram_message(position_id, "strat1", "Test Strategy", trigger_type, "msg text", success, None, sent_at)


def test_never_sent_any_signal_is_stale(test_db):
    status = telegram_bot.no_signal_alert_status()
    assert status["stale"] is True
    assert status["last_sent_at"] is None
    assert "yet" in status["message"]


def test_a_signal_sent_23_hours_ago_is_not_stale(test_db):
    now = datetime.now(timezone.utc)
    _log("automatic", 1, _iso(now - timedelta(hours=23)))
    status = telegram_bot.no_signal_alert_status(now_iso=_iso(now))
    assert status["stale"] is False
    assert status["message"] is None


def test_exactly_at_the_24_hour_mark_triggers(test_db):
    """The boundary itself counts as stale (>=), not just strictly past it."""
    now = datetime.now(timezone.utc)
    _log("manual", 1, _iso(now - timedelta(hours=24)))
    status = telegram_bot.no_signal_alert_status(now_iso=_iso(now))
    assert status["stale"] is True
    assert status["hours_since"] == 24.0
    assert "24 hours" in status["message"]


def test_a_signal_sent_25_hours_ago_is_stale(test_db):
    now = datetime.now(timezone.utc)
    _log("automatic", 1, _iso(now - timedelta(hours=25)))
    status = telegram_bot.no_signal_alert_status(now_iso=_iso(now))
    assert status["stale"] is True
    assert status["hours_since"] == 25.0


def test_alert_clears_the_moment_a_new_signal_sends(test_db):
    now = datetime.now(timezone.utc)
    _log("automatic", 1, _iso(now - timedelta(hours=30)))
    stale_before = telegram_bot.no_signal_alert_status(now_iso=_iso(now))
    assert stale_before["stale"] is True

    # a fresh signal sends right now
    _log("automatic", 1, _iso(now))
    status_after = telegram_bot.no_signal_alert_status(now_iso=_iso(now))
    assert status_after["stale"] is False
    assert status_after["message"] is None


def test_manual_send_clears_the_alert(test_db):
    """"Any tier" -- a manual send resets the clock exactly like an
    automatic high/low tier send does."""
    now = datetime.now(timezone.utc)
    _log("manual", 1, _iso(now - timedelta(minutes=5)))
    status = telegram_bot.no_signal_alert_status(now_iso=_iso(now))
    assert status["stale"] is False


def test_failed_send_attempts_do_not_count_as_a_real_signal(test_db):
    """A failed send (network error, bad token) never actually reached
    Telegram -- it must not falsely clear the alert."""
    now = datetime.now(timezone.utc)
    _log("automatic", 0, _iso(now - timedelta(minutes=5)))  # failed
    status = telegram_bot.no_signal_alert_status(now_iso=_iso(now))
    assert status["stale"] is True
    assert status["last_sent_at"] is None


def test_close_followup_messages_do_not_count_as_a_new_signal(test_db):
    """A close_followup is a RESULT notification about an already-sent
    signal, not a new signal -- it must not reset the drought clock."""
    now = datetime.now(timezone.utc)
    _log("automatic", 1, _iso(now - timedelta(hours=30)))  # the actual last real signal
    _log("close_followup", 1, _iso(now - timedelta(minutes=1)))  # a result message, not a new signal
    status = telegram_bot.no_signal_alert_status(now_iso=_iso(now))
    assert status["stale"] is True
    assert status["hours_since"] == 30.0


def test_get_last_telegram_signal_sent_at_returns_none_when_empty(test_db):
    assert storage.get_last_telegram_signal_sent_at() is None


def test_get_last_telegram_signal_sent_at_returns_the_most_recent(test_db):
    now = datetime.now(timezone.utc)
    _log("manual", 1, _iso(now - timedelta(hours=5)))
    _log("automatic", 1, _iso(now - timedelta(hours=1)))
    _log("manual", 1, _iso(now - timedelta(hours=10)))
    assert storage.get_last_telegram_signal_sent_at() == _iso(now - timedelta(hours=1))
