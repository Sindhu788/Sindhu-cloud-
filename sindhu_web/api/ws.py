from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from sindhu_web import auth, broadcast, devices, session_guard
from sindhu_web.security import _is_lan_client

router = APIRouter()

# Task 2 (single active session): a second connection from the same
# device closes the first with this code so the client can tell "you were
# replaced by a newer tab" apart from an ordinary network drop and skip
# its usual auto-reconnect. See sindhu_web/session_guard.py for what
# "device" means here and why it's scoped that way.
SUPERSEDED_CLOSE_CODE = 4409


@router.websocket("/ws/logs")
async def logs_ws(websocket: WebSocket):
    """One channel for everything live: log lines, job started/finished
    events, per-job progress updates, and sync events (strategy/lesson/
    settings changes) -- each message carries a "channel" field so the
    frontend can route it. Also registers this connection as a "connected
    device" for the Control Center, for as long as the socket stays open.

    SECURITY: sindhu_web.security.token_guard_middleware is an HTTP-only
    middleware (`@app.middleware("http")`) -- Starlette never runs it for
    a WebSocket upgrade, so the login-session gate that protects every
    other page and API endpoint has never actually applied here. On the
    local laptop this went unnoticed because the LAN check below already
    limited this socket to the same WiFi network. Once SINDHU_CLOUD_MODE
    bypasses that LAN check for a public cloud deployment (Railway),
    relying on it alone here would leave this one socket reachable by
    anyone on the internet with zero login required -- a live feed of
    every trade, log line, and Telegram send. This explicit session check
    is what actually closes that gap, on both the local app and the cloud
    one, rather than depending on network topology to do a login gate's
    job."""
    ip = websocket.client.host if websocket.client else None
    if not _is_lan_client(ip):
        await websocket.close(code=4403)
        return
    if not auth.is_valid_session(websocket.cookies.get(auth.SESSION_COOKIE)):
        await websocket.close(code=4401)
        return

    device_id = websocket.query_params.get("device_id")
    await websocket.accept()

    superseded = session_guard.claim(device_id, websocket)
    if superseded is not None:
        try:
            await superseded.close(code=SUPERSEDED_CLOSE_CODE, reason="superseded-by-new-session")
        except Exception:
            pass

    broadcast.clients.add(websocket)
    ip = ip or "unknown"
    user_agent = websocket.headers.get("user-agent", "unknown")
    devices.register(websocket, ip, user_agent)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        broadcast.clients.discard(websocket)
        devices.unregister(websocket)
        session_guard.release(device_id, websocket)
