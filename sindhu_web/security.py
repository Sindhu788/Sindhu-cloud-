"""Lightweight protection appropriate for a single-user local/LAN tool --
not full auth infrastructure. Read-only GET requests are always open (so
phones/tablets on the same network can view dashboards without friction);
any state-changing request must carry the token this server generated for
itself on first run, which the frontend picks up automatically from the
page it was served."""

import ipaddress
import json
import os
import secrets

from fastapi import Request
from fastapi.responses import JSONResponse

from data_engine.paths import CONFIG_DIR, ensure_folders

_TOKEN_PATH = os.path.join(CONFIG_DIR, "api_token.json")

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_EXEMPT_PATHS = {"/", "/api/token"}


def _is_lan_client(host):
    """True for loopback (same machine) or any private LAN range
    (192.168.x.x, 10.x.x.x, 172.16-31.x.x) -- i.e. "same WiFi network".
    Anything else (a real internet address) is refused outright."""
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private


def get_or_create_token():
    ensure_folders()
    if os.path.exists(_TOKEN_PATH):
        with open(_TOKEN_PATH, "r", encoding="utf-8") as f:
            return json.load(f)["token"]
    token = secrets.token_hex(16)
    with open(_TOKEN_PATH, "w", encoding="utf-8") as f:
        json.dump({"token": token}, f)
    return token


async def token_guard_middleware(request: Request, call_next):
    client_host = request.client.host if request.client else None
    if not _is_lan_client(client_host):
        return JSONResponse({"detail": "access restricted to the local network"}, status_code=403)

    if request.method in _SAFE_METHODS or request.url.path in _EXEMPT_PATHS \
            or request.url.path.startswith("/static") or request.url.path.startswith("/ws"):
        return await call_next(request)

    expected = get_or_create_token()
    provided = request.headers.get("x-sindhu-token")
    if provided != expected:
        return JSONResponse({"detail": "missing or invalid X-Sindhu-Token header"}, status_code=401)
    return await call_next(request)
