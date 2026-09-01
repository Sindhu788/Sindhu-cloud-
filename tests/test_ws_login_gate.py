"""sindhu_web/api/ws.py -- the /ws/logs WebSocket must require a valid
login session, not just the LAN check.

Why this matters: sindhu_web.security.token_guard_middleware is an
HTTP-only middleware (`@app.middleware("http")`) -- Starlette never runs
it for a WebSocket upgrade, so the login gate that protects every other
page and API endpoint never actually applied to this socket. That went
unnoticed locally because the LAN check already limited it to the same
WiFi network -- but the lightweight cloud runner's SINDHU_CLOUD_MODE flag
(see sindhu_web/security.py) bypasses that LAN check entirely for a public
Railway deployment, which would have left this one socket reachable by
anyone on the internet with zero login required. These tests pin down the
fix: an explicit session check inside the handler itself.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from sindhu_web import auth
from sindhu_web.api import ws


def _fake_websocket(cookies=None, client_host="127.0.0.1"):
    fake = MagicMock()
    fake.client.host = client_host
    fake.cookies = cookies or {}
    fake.query_params = {}
    fake.headers = {}
    fake.accept = AsyncMock()
    fake.close = AsyncMock()
    # Ends the connection immediately once accepted, so the test doesn't
    # hang inside the handler's `while True: receive_text()` loop.
    fake.receive_text = AsyncMock(side_effect=ws.WebSocketDisconnect())
    return fake


def test_no_session_cookie_is_refused_even_from_a_lan_ip(monkeypatch):
    monkeypatch.setattr(ws, "_is_lan_client", lambda ip: True)
    fake = _fake_websocket(cookies={})

    asyncio.run(ws.logs_ws(fake))

    fake.close.assert_awaited_once_with(code=4401)
    fake.accept.assert_not_awaited()


def test_invalid_session_cookie_is_refused(monkeypatch):
    monkeypatch.setattr(ws, "_is_lan_client", lambda ip: True)
    monkeypatch.setattr(auth, "is_valid_session", lambda token: False)
    fake = _fake_websocket(cookies={auth.SESSION_COOKIE: "garbage-token"})

    asyncio.run(ws.logs_ws(fake))

    fake.close.assert_awaited_once_with(code=4401)
    fake.accept.assert_not_awaited()


def test_valid_session_and_lan_is_accepted(monkeypatch):
    monkeypatch.setattr(ws, "_is_lan_client", lambda ip: True)
    monkeypatch.setattr(auth, "is_valid_session", lambda token: token == "real-token")
    monkeypatch.setattr(ws.session_guard, "claim", lambda device_id, sock: None)
    monkeypatch.setattr(ws.session_guard, "release", lambda device_id, sock: None)
    monkeypatch.setattr(ws.devices, "register", lambda *a, **k: None)
    monkeypatch.setattr(ws.devices, "unregister", lambda *a, **k: None)
    fake = _fake_websocket(cookies={auth.SESSION_COOKIE: "real-token"})

    asyncio.run(ws.logs_ws(fake))

    fake.accept.assert_awaited_once()
    fake.close.assert_not_awaited()


def test_non_lan_client_is_refused_before_the_session_check_even_runs(monkeypatch):
    """The network check still comes first (cheaper, no cookie parsing
    needed) -- this is the existing local-laptop behavior, unchanged."""
    monkeypatch.setattr(ws, "_is_lan_client", lambda ip: False)
    session_check = MagicMock(return_value=True)
    monkeypatch.setattr(auth, "is_valid_session", session_check)
    fake = _fake_websocket(cookies={auth.SESSION_COOKIE: "real-token"}, client_host="8.8.8.8")

    asyncio.run(ws.logs_ws(fake))

    fake.close.assert_awaited_once_with(code=4403)
    session_check.assert_not_called()


def test_cloud_mode_without_a_session_still_refuses_the_socket(monkeypatch):
    """The scenario this fix exists for: SINDHU_CLOUD_MODE has already
    made _is_lan_client() always True (see sindhu_web/security.py), so an
    anonymous internet visitor with no session cookie must still be
    refused by the check this test exercises directly."""
    monkeypatch.setattr(ws, "_is_lan_client", lambda ip: True)  # simulates CLOUD_MODE's effect
    fake = _fake_websocket(cookies={}, client_host="203.0.113.7")

    asyncio.run(ws.logs_ws(fake))

    fake.close.assert_awaited_once_with(code=4401)
    fake.accept.assert_not_awaited()
