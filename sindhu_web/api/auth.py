"""Login gate endpoints (Master Task 2, Part 5). See sindhu_web/auth.py for
the credential/session logic and sindhu_web/security.py for the middleware
that actually enforces the gate on every other request."""

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from sindhu_web import auth

router = APIRouter()


class AuthPayload(BaseModel):
    username: str
    password: str


class ChangePasswordPayload(BaseModel):
    current_password: str
    new_password: str


def _set_session_cookie(response: Response, token: str, secure: bool = False):
    response.set_cookie(
        auth.SESSION_COOKIE, token, httponly=True, samesite="lax", secure=secure,
        max_age=60 * 60 * 24 * auth.SESSION_LIFETIME_DAYS,
    )


def _is_https(request: Request) -> bool:
    # Render terminates TLS in front of the app and says so in X-Forwarded-Proto; the cookie may then be marked Secure.
    return request.headers.get("x-forwarded-proto", request.url.scheme) == "https"


# ---- login throttle (Day 4 security review): in memory, per client address and overall; slows password guessing without a lockout
# that an attacker could use against the owner (a block expires by itself after WINDOW seconds).
import threading as _threading
import time as _time

_LOGIN_WINDOW_S = 600
_LOGIN_MAX_PER_CLIENT = 8
_LOGIN_MAX_TOTAL = 40
_fail_lock = _threading.Lock()
_fails = {}          # key -> [timestamps of recent failures]


def _client_key(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return (fwd.split(",")[0].strip() or (request.client.host if request.client else "?"))


def _recent(key, now):
    lst = [t for t in _fails.get(key, []) if now - t < _LOGIN_WINDOW_S]
    _fails[key] = lst
    return lst


def _login_blocked(request: Request) -> bool:
    now = _time.time()
    with _fail_lock:
        return len(_recent(_client_key(request), now)) >= _LOGIN_MAX_PER_CLIENT or len(_recent("*", now)) >= _LOGIN_MAX_TOTAL


def _login_failed(request: Request):
    now = _time.time()
    with _fail_lock:
        for k in (_client_key(request), "*"):
            _recent(k, now).append(now)


def _login_ok(request: Request):
    with _fail_lock:
        _fails.pop(_client_key(request), None)


@router.get("/api/auth/status")
def auth_status(request: Request):
    token = request.cookies.get(auth.SESSION_COOKIE)
    logged_in = auth.is_valid_session(token)
    # Investigation Batch 2026-09-17, item 1.7: session_expires_at is only
    # meaningful (and only looked up) for a genuinely valid session -- an
    # invalid/missing token already redirects to /login well before this
    # would matter, and a raw expiry from a stale/expired token row would
    # be misleading (already in the past) rather than useful.
    expires_at = auth.session_expires_at(token) if logged_in else None
    return {
        "configured": auth.has_credentials(),
        "logged_in": logged_in,
        "session_expires_at": expires_at,
    }


@router.post("/api/auth/setup")
def auth_setup(req: AuthPayload, response: Response):
    """First-run only -- creates the one account. Refuses once an account
    already exists (change it via /api/auth/change-password instead, which
    requires already being logged in)."""
    if auth.has_credentials():
        raise HTTPException(400, "An account is already configured -- use login instead.")
    username = req.username.strip()
    if not username:
        raise HTTPException(400, "Username is required.")
    if len(req.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters.")
    auth.set_credentials(username, req.password)
    token = auth.create_session()
    _set_session_cookie(response, token)
    return {"ok": True}


@router.post("/api/auth/login")
def auth_login(req: AuthPayload, response: Response, request: Request):
    if _login_blocked(request):
        raise HTTPException(429, "Too many failed sign-in attempts. Wait 10 minutes and try again.")
    if not auth.verify_password(req.username.strip(), req.password):
        _login_failed(request)
        raise HTTPException(401, "Incorrect username or password.")
    _login_ok(request)
    token = auth.create_session()
    _set_session_cookie(response, token, _is_https(request))
    return {"ok": True}


@router.post("/api/auth/logout")
def auth_logout(request: Request, response: Response):
    token = request.cookies.get(auth.SESSION_COOKIE)
    if token:
        auth.invalidate_session(token)
    response.delete_cookie(auth.SESSION_COOKIE)
    return {"ok": True}


@router.post("/api/auth/change-password")
def auth_change_password(req: ChangePasswordPayload):
    if len(req.new_password) < 8:
        raise HTTPException(400, "New password must be at least 8 characters.")
    if not auth.change_password(req.current_password, req.new_password):
        raise HTTPException(401, "Current password is incorrect.")
    return {"ok": True}
