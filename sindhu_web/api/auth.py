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


def _set_session_cookie(response: Response, token: str):
    response.set_cookie(
        auth.SESSION_COOKIE, token, httponly=True, samesite="lax",
        max_age=60 * 60 * 24 * auth.SESSION_LIFETIME_DAYS,
    )


@router.get("/api/auth/status")
def auth_status(request: Request):
    token = request.cookies.get(auth.SESSION_COOKIE)
    return {
        "configured": auth.has_credentials(),
        "logged_in": auth.is_valid_session(token),
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
def auth_login(req: AuthPayload, response: Response):
    if not auth.verify_password(req.username.strip(), req.password):
        raise HTTPException(401, "Incorrect username or password.")
    token = auth.create_session()
    _set_session_cookie(response, token)
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
