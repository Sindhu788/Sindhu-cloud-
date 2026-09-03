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
from datetime import datetime, timezone

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse

from data_engine.config import env_flag
from data_engine.paths import CONFIG_DIR, ensure_folders
from sindhu_web import auth

_TOKEN_PATH = os.path.join(CONFIG_DIR, "api_token.json")
_TOKEN_CLOUD_SETTING_KEY = "api_token"

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_EXEMPT_PATHS = {"/", "/api/token"}

# Master Task 2, Part 5: the login page itself and everything it needs to
# function BEFORE a session exists -- must stay reachable while logged out.
# "/" is deliberately NOT here: index() in server.py decides whether "/"
# serves the dashboard or redirects to /login based on session state, so
# the dashboard's own HTML is never handed out to a logged-out request.
#
# "/health" (lightweight cloud runner only -- see cloud_runtime/app.py) is
# here so an external uptime pinger (e.g. cron-job.org, hitting it every
# few minutes to stop a free-tier host from sleeping the app after 15
# minutes of inactivity) never needs credentials. It reveals nothing
# beyond "the process is up" -- no trading data, no settings, not even
# whether an account has been configured yet.
_LOGIN_EXEMPT_PATHS = {"/login", "/api/auth/status", "/api/auth/setup", "/api/auth/login", "/health"}

# A valid session cookie is a stronger signal than the X-Sindhu-Token
# header below (which exists to distinguish a real browser request from a
# random LAN script) -- these two endpoints are meaningless without
# already being logged in, so they still go through the session check
# above like any other request, they just don't ALSO need the separate
# token header on top of that.
_SESSION_AUTHENTICATES_PATHS = {"/api/auth/logout", "/api/auth/change-password"}


# Lightweight cloud runner support: on the local laptop this stays exactly
# what it always was -- LAN-only, unconditionally. A cloud deployment (e.g.
# Railway) is reached over the real internet by definition, so the LAN
# check would refuse every single visitor including the CEO -- there is no
# "same WiFi network" concept once the app is on a public host. Setting
# SINDHU_CLOUD_MODE=1 (an explicit, separate flag from DATABASE_URL/
# SINDHU_LIVE_CANDLES, so accidentally setting one of THOSE locally for
# testing can never also loosen this) is the ONLY way to bypass the LAN
# check, and it bypasses ONLY the LAN check -- the login-session gate right
# below this in the middleware still runs unconditionally either way, so a
# cloud deployment is never reachable by anyone who hasn't logged in.
CLOUD_MODE = env_flag("SINDHU_CLOUD_MODE")


def _is_lan_client(host):
    """True for loopback (same machine) or any private LAN range
    (192.168.x.x, 10.x.x.x, 172.16-31.x.x) -- i.e. "same WiFi network".
    Anything else (a real internet address) is refused outright.

    Bypassed entirely when CLOUD_MODE is on (see above) -- the login page
    becomes the sole access control in that case, exactly as Step 1 of the
    Railway deployment task requires."""
    if CLOUD_MODE:
        return True
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private


def get_or_create_token():
    """Master Task 3, Phase 0.3: on a host with DATABASE_URL set (Postgres),
    this is persisted in the cloud_settings table instead of the local file
    below -- the local file lives on Render's ephemeral filesystem, wiped on
    every restart/redeploy/sleep-wake. A browser tab that already cached the
    old token in localStorage would then send a now-invalid X-Sindhu-Token
    on every state-changing request (Start/Stop Engine, Dry Run toggle,
    ...), which the server correctly rejects with 401 -- from the CEO's
    side this looked exactly like "the buttons don't respond." Same
    Postgres-backed persistence pattern already used for login credentials/
    sessions and Paper Trading settings (see paper_trading/config.py's
    identical comment). Local laptop behavior (DATABASE_URL unset) is
    completely unchanged."""
    from data_engine import db_backend, storage

    if db_backend.IS_POSTGRES:
        saved = storage.get_cloud_setting(_TOKEN_CLOUD_SETTING_KEY)
        if saved and saved.get("token"):
            return saved["token"]
        token = secrets.token_hex(16)
        storage.save_cloud_setting(
            _TOKEN_CLOUD_SETTING_KEY, {"token": token}, datetime.now(timezone.utc).isoformat()
        )
        return token

    ensure_folders()
    if os.path.exists(_TOKEN_PATH):
        with open(_TOKEN_PATH, "r", encoding="utf-8") as f:
            return json.load(f)["token"]
    token = secrets.token_hex(16)
    with open(_TOKEN_PATH, "w", encoding="utf-8") as f:
        json.dump({"token": token}, f)
    return token


async def token_guard_middleware(request: Request, call_next):
    path = request.url.path

    # "/health" must survive even a MISCONFIGURED cloud deploy (e.g.
    # SINDHU_CLOUD_MODE not actually set) -- otherwise the one endpoint
    # meant to let the CEO/an uptime pinger diagnose exactly that problem
    # is itself blocked by it, a chicken-and-egg dead end confirmed live:
    # a real deploy had CLOUD_MODE evaluating False and /health returned
    # the SAME "access restricted to the local network" error as every
    # other path, with no way to see cloud_mode's real value without
    # dashboard/log access. Checked BEFORE the LAN gate below (not just
    # the login gate further down) -- it reveals nothing sensitive (no
    # trading data, no settings, not even whether an account exists), so
    # bypassing the LAN check for it unconditionally costs nothing.
    if path == "/health":
        return await call_next(request)

    client_host = request.client.host if request.client else None
    if not _is_lan_client(client_host):
        return JSONResponse({"detail": "access restricted to the local network"}, status_code=403)

    # Master Task 2, Part 5: the login gate. Unlike the token check below
    # (which only ever guarded state-changing requests), this applies to
    # EVERY method including GET -- no dashboard page and no API response
    # is handed out to a request without a valid session. "/" is
    # deliberately excluded here: server.py's index() itself decides
    # whether to serve the dashboard or redirect to /login, so the
    # dashboard's own HTML is still never reached without a session, it's
    # just decided one layer up. Static files stay reachable (app.js/
    # app.css are code, not data -- serving them pre-login leaks nothing,
    # and the login page needs this same static mount available too).
    if path != "/" and path not in _LOGIN_EXEMPT_PATHS and not path.startswith("/static"):
        session_token = request.cookies.get(auth.SESSION_COOKIE)
        if not auth.is_valid_session(session_token):
            if request.method in _SAFE_METHODS and not path.startswith("/api/") and not path.startswith("/ws"):
                return RedirectResponse(url="/login")
            return JSONResponse({"detail": "login required"}, status_code=401)

    if request.method in _SAFE_METHODS or path in _EXEMPT_PATHS or path in _LOGIN_EXEMPT_PATHS \
            or path in _SESSION_AUTHENTICATES_PATHS \
            or path.startswith("/static") or path.startswith("/ws"):
        return await call_next(request)

    expected = get_or_create_token()
    provided = request.headers.get("x-sindhu-token")
    if provided != expected:
        return JSONResponse({"detail": "missing or invalid X-Sindhu-Token header"}, status_code=401)
    return await call_next(request)
