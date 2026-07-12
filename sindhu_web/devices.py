"""Tracks which devices currently have the dashboard open (one entry per
live WebSocket connection) -- backs the Control Center's "Connected
Devices" list. Purely in-memory; a disconnect (tab closed, phone locked)
removes the entry."""

import threading
from datetime import datetime, timezone

_lock = threading.Lock()
_devices = {}


def register(ws, ip, user_agent):
    with _lock:
        _devices[id(ws)] = {
            "ip": ip,
            "user_agent": user_agent,
            "connected_at": datetime.now(timezone.utc).isoformat(),
        }


def unregister(ws):
    with _lock:
        _devices.pop(id(ws), None)


def list_devices():
    with _lock:
        return list(_devices.values())
