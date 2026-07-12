from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from sindhu_web import broadcast, devices
from sindhu_web.security import _is_lan_client

router = APIRouter()


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

    await websocket.accept()
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
