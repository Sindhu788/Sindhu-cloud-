"""Master 15-Item task, Item 6: Emergency Downtime Alert watchdog.

Simulates real failure/recovery sequences against scripts/uptime_watchdog.py's
run_check() -- the HTTP layer (requests.get) is monkeypatched to deterministic
up/down responses (a real, unmocked network call would make this test flaky
and dependent on an actual outage happening at the exact moment CI runs), but
the alert-decision logic itself (consecutive-failure counting, one-alert-per-
outage, recovery message) is the REAL code, unmocked, and send_fn is a
recording stub so we can verify exactly when and what it would have sent
without needing live Telegram credentials.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts import uptime_watchdog


class _FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    state_path = str(tmp_path / "uptime_watchdog_state.json")
    monkeypatch.setattr(uptime_watchdog, "STATE_PATH", state_path)
    yield state_path


def _recording_send_fn(calls):
    def _send(text):
        calls.append(text)
        return {"ok": True, "error": None}
    return _send


def test_single_failure_below_threshold_does_not_alert(monkeypatch):
    monkeypatch.setattr(uptime_watchdog, "check_health", lambda url: (False, "unreachable: Connection refused"))
    calls = []
    result = uptime_watchdog.run_check(threshold=3, send_fn=_recording_send_fn(calls))
    assert result["is_up"] is False
    assert result["alert_sent"] is None
    assert calls == []
    assert result["state_after"]["consecutive_failures"] == 1


def test_real_simulated_outage_triggers_exactly_one_alert_at_threshold(monkeypatch):
    """Genuine simulated failure: 5 consecutive down checks with
    threshold=3 -- the alert must fire on the 3rd check, and NEVER again
    on the 4th/5th (one alert per outage, not spammed every run)."""
    monkeypatch.setattr(uptime_watchdog, "check_health", lambda url: (False, "unreachable: Connection refused"))
    calls = []
    send_fn = _recording_send_fn(calls)

    results = [uptime_watchdog.run_check(threshold=3, send_fn=send_fn) for _ in range(5)]

    alert_fired_at = [i for i, r in enumerate(results, start=1) if r["alert_sent"] == "down"]
    assert alert_fired_at == [3], f"expected exactly one 'down' alert on check #3, got {alert_fired_at}"
    assert len(calls) == 1
    assert "DOWN" in calls[0]
    assert "3 consecutive failed health checks" in calls[0]
    # still down on checks 4 and 5 -- no second alert
    assert results[3]["alert_sent"] is None
    assert results[4]["alert_sent"] is None


def test_recovery_after_alerted_outage_sends_one_recovery_message(monkeypatch):
    calls = []
    send_fn = _recording_send_fn(calls)

    monkeypatch.setattr(uptime_watchdog, "check_health", lambda url: (False, "unreachable: Connection refused"))
    for _ in range(3):
        uptime_watchdog.run_check(threshold=3, send_fn=send_fn)
    assert len(calls) == 1  # the "down" alert already sent

    monkeypatch.setattr(uptime_watchdog, "check_health", lambda url: (True, '{"status": "ok"}'))
    recovery_result = uptime_watchdog.run_check(threshold=3, send_fn=send_fn)

    assert recovery_result["alert_sent"] == "recovery"
    assert len(calls) == 2
    assert "back UP" in calls[1]
    assert recovery_result["state_after"]["consecutive_failures"] == 0
    assert recovery_result["state_after"]["alerted_this_outage"] is False

    # a SECOND consecutive "up" check must not re-send anything
    second_up_result = uptime_watchdog.run_check(threshold=3, send_fn=send_fn)
    assert second_up_result["alert_sent"] is None
    assert len(calls) == 2


def test_recovery_before_reaching_threshold_never_alerts(monkeypatch):
    """A short blip (2 failures, threshold=3) that recovers before the
    threshold is reached must never send anything at all -- neither a
    down alert (never reached) nor a recovery message (nothing to
    recover FROM, from the CEO's perspective)."""
    calls = []
    send_fn = _recording_send_fn(calls)

    monkeypatch.setattr(uptime_watchdog, "check_health", lambda url: (False, "unreachable"))
    uptime_watchdog.run_check(threshold=3, send_fn=send_fn)
    uptime_watchdog.run_check(threshold=3, send_fn=send_fn)

    monkeypatch.setattr(uptime_watchdog, "check_health", lambda url: (True, '{"status": "ok"}'))
    result = uptime_watchdog.run_check(threshold=3, send_fn=send_fn)

    assert result["alert_sent"] is None
    assert calls == []


def test_state_persists_across_separate_invocations(monkeypatch, isolated_state):
    """Each run_check() call is a fresh process in real usage (a scheduled
    task) -- state must survive via the JSON file, not just in-memory."""
    monkeypatch.setattr(uptime_watchdog, "check_health", lambda url: (False, "unreachable"))
    uptime_watchdog.run_check(threshold=3, send_fn=_recording_send_fn([]))
    assert os.path.exists(isolated_state)
    with open(isolated_state, encoding="utf-8") as f:
        saved = json.load(f)
    assert saved["consecutive_failures"] == 1
    assert saved["last_status"] == "down"


def test_check_health_against_a_real_unreachable_port():
    """The one non-mocked check: a genuinely real, unreachable local
    address (a closed port on localhost, guaranteed to refuse the
    connection) proves check_health()'s actual HTTP/exception-handling
    code path works against a REAL failure, not just a monkeypatched one."""
    is_up, detail = uptime_watchdog.check_health("http://127.0.0.1:1/health")
    assert is_up is False
    assert detail  # some real error detail captured, not silently empty
