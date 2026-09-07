"""Master 15-Item task, Item 8: Mobile Push Notifications decision --
ntfy.sh (see paper_trading/push_notifications.py's own docstring for why
over browser Web Push). Tests the not-configured-yet guard with mocked
settings, then proves the real HTTP mechanism works with one real POST
to ntfy.sh's real public infrastructure using a disposable, randomly-
generated throwaway topic (nobody is subscribed to it, and it is never
saved as the CEO's real configured ntfy_topic) -- real evidence the
integration works without directing any notification at a real person,
consistent with this session's own policy of not sending messages on the
CEO's behalf without their explicit permission first."""
import uuid

import pytest
import requests

from paper_trading import push_notifications


def test_no_topic_configured_returns_clear_error(monkeypatch):
    monkeypatch.setattr(push_notifications.pt_config, "load", lambda: {"ntfy_topic": ""})
    result = push_notifications.send_push("Test", "message")
    assert result["ok"] is False
    assert "not configured" in result["error"]


def test_real_post_to_ntfy_with_a_disposable_throwaway_topic(monkeypatch):
    """Real network call, real ntfy.sh response -- proves the send_push()
    HTTP mechanics (headers, encoding, status handling) actually work
    end-to-end. Uses a one-off random topic name that is never persisted
    anywhere and has no subscribers, so this never reaches a real
    person -- it only proves the plumbing works."""
    throwaway_topic = f"sindhu-mechanism-test-{uuid.uuid4().hex}"
    monkeypatch.setattr(push_notifications.pt_config, "load", lambda: {"ntfy_topic": throwaway_topic})
    try:
        result = push_notifications.send_push("SINDHU mechanism test", "real HTTP test, no real recipient")
    except requests.RequestException:
        pytest.skip("no network access available in this environment to reach ntfy.sh")
    if not result["ok"] and "RequestException" in (result.get("error") or ""):
        pytest.skip(f"ntfy.sh unreachable from this environment: {result['error']}")
    assert result["ok"] is True, result.get("error")
    assert result["error"] is None
