from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from sindhu_web import broadcast, devices, session_guard
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
    device" for the Control Center, for as long as the socket stays open."""
    ip = websocket.client.host if websocket.client else None
    if not _is_lan_client(ip):
        await websocket.close(code=4403)
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
