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


def _fake_ntfy(status=200, body=b"ok"):
    """Day 8: a local stand-in for ntfy.sh on its OWN free port, recording what send_push really put on the wire (method, path, headers, body bytes)."""
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    seen = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            seen.append({"path": self.path, "title": self.headers.get("Title"), "priority": self.headers.get("Priority"), "body": self.rfile.read(n)})
            self.send_response(status); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, seen, f"http://127.0.0.1:{srv.server_address[1]}"


def test_send_push_http_mechanics_against_a_local_stand_in_server(monkeypatch):
    """Deterministic replacement (Day 8) of the old test that posted to the real ntfy.sh: no internet, no rate limits, no dependence on another service.
    Checks what really goes on the wire: POST to /<topic>, Title and Priority headers, the message as UTF-8 bytes (including non-ASCII), and the
    handling of success, an HTTP error and an unreachable server."""
    srv, seen, base = _fake_ntfy(200)
    try:
        monkeypatch.setattr(push_notifications, "NTFY_BASE_URL", base)
        monkeypatch.setattr(push_notifications.pt_config, "load", lambda: {"ntfy_topic": "sindhu-test-topic"})
        result = push_notifications.send_push("SINDHU mechanism test", "alert ✓ سلام", priority="high")
        assert result == {"ok": True, "error": None}
        assert seen == [{"path": "/sindhu-test-topic", "title": "SINDHU mechanism test", "priority": "high", "body": "alert ✓ سلام".encode("utf-8")}]
    finally:
        srv.shutdown(); srv.server_close()
    srv2, _, base2 = _fake_ntfy(429, b"rate limited")
    try:
        monkeypatch.setattr(push_notifications, "NTFY_BASE_URL", base2)
        bad = push_notifications.send_push("t", "m")
        assert bad["ok"] is False and bad["error"].startswith("HTTP 429") and "rate limited" in bad["error"]
    finally:
        srv2.shutdown(); srv2.server_close()
    monkeypatch.setattr(push_notifications, "NTFY_BASE_URL", base2)                       # that server is now shut down: nothing listens there
    gone = push_notifications.send_push("t", "m")
    assert gone["ok"] is False and "RequestException" in gone["error"] or "Error" in gone["error"]


def test_real_post_to_ntfy_with_a_disposable_throwaway_topic(monkeypatch):
    """OPT-IN live check (set SINDHU_LIVE_NETWORK_TESTS=1): real network call to the real ntfy.sh with a one-off random topic nobody subscribes to.
    It is not part of the normal suite any more because a public service can rate-limit or be unreachable, which made the suite flaky."""
    import os
    if os.environ.get("SINDHU_LIVE_NETWORK_TESTS") != "1":
        pytest.skip("live-network test: set SINDHU_LIVE_NETWORK_TESTS=1 to run it")
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
