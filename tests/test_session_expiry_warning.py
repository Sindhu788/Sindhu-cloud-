"""Investigation Batch 2026-09-17, item 1.7: the dashboard had no warning
before a forced logout -- a session's 30-day cookie (sindhu_web.auth.
SESSION_LIFETIME_DAYS) just silently expired, and the next request got a
401/redirect to /login with zero notice. auth.session_expires_at() and
/api/auth/status's new session_expires_at field are the backend half of
the fix; sindhu_web/static/js/app.js polls this and shows a banner once
expiry is within 24h (see app.js's SESSION_EXPIRY_WARNING_HOURS)."""

from datetime import datetime, timedelta, timezone

import pytest

from data_engine import config as base_config
from sindhu_web import auth


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def test_expires_at_is_none_for_no_token():
    assert auth.session_expires_at(None) is None
    assert auth.session_expires_at("") is None


def test_expires_at_is_none_for_an_unknown_token():
    assert auth.session_expires_at("not-a-real-token") is None


def test_expires_at_matches_what_create_session_wrote():
    token = auth.create_session()
    expires_at = auth.session_expires_at(token)
    assert expires_at is not None
    parsed = datetime.fromisoformat(expires_at)
    expected = datetime.now(timezone.utc) + timedelta(days=auth.SESSION_LIFETIME_DAYS)
    # Within a minute of "now + 30 days" -- real, not a placeholder value.
    assert abs((parsed - expected).total_seconds()) < 60


def test_expires_at_survives_after_invalidation_query_returns_none():
    token = auth.create_session()
    auth.invalidate_session(token)
    assert auth.is_valid_session(token) is False
    assert auth.session_expires_at(token) is None


def _fake_request(cookie_header=None):
    """Same no-httpx-needed pattern tests/test_cloud_runtime.py already
    uses for a Request-taking endpoint: a raw ASGI scope, no test HTTP
    client (starlette.testclient needs httpx2, not installed here)."""
    from fastapi import Request
    headers = [(b"cookie", cookie_header.encode())] if cookie_header else []
    scope = {
        "type": "http", "method": "GET", "path": "/api/auth/status",
        "headers": headers, "query_string": b"", "client": ("127.0.0.1", 1),
    }
    return Request(scope)


def test_auth_status_endpoint_includes_session_expires_at_when_logged_in(test_db):
    from sindhu_web.api.auth import auth_status

    auth.set_credentials("ceo", "a-real-password-123")
    token = auth.create_session()

    body = auth_status(_fake_request(f"{auth.SESSION_COOKIE}={token}"))
    assert body["logged_in"] is True
    assert body["session_expires_at"] is not None
    # A real future timestamp, not a placeholder.
    parsed = datetime.fromisoformat(body["session_expires_at"])
    assert parsed > datetime.now(timezone.utc)


def test_auth_status_endpoint_omits_session_expires_at_when_logged_out(test_db):
    from sindhu_web.api.auth import auth_status

    body = auth_status(_fake_request())
    assert body["logged_in"] is False
    assert body["session_expires_at"] is None
