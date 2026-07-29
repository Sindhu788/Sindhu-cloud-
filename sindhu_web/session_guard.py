"""Task 2 (single active session): keeps at most one live /ws/logs
connection per *device*. "Device" here means one browser profile on one
computer -- the client mints a UUID into localStorage (sindhu_device_id),
so every tab/window opened on the SAME computer shares that id, but a
phone or a different PC always gets its own. This is deliberately
narrower than "one session for the whole account": the existing, already
built and verified "Connect from mobile (same WiFi)" feature depends on a
phone and the desktop dashboard staying connected at the same time, and a
literal single-global-session rule would silently break that. Opening a
second tab on the SAME device closes the first (so two tabs never
silently fight over the same background actions); a second, different
device is completely unaffected."""

import threading

_lock = threading.Lock()
_active = {}  # device_id -> WebSocket


def claim(device_id, ws):
    """Registers `ws` as the active connection for `device_id`, evicting
    whatever connection previously held that slot. Returns the previous
    WebSocket to close, or None if there wasn't one (or `device_id` is
    falsy, e.g. an older client build with no device_id yet -- treated as
    "no session guard" rather than erroring)."""
    if not device_id:
        return None
    with _lock:
        previous = _active.get(device_id)
        _active[device_id] = ws
    return previous if previous is not ws else None


def release(device_id, ws):
    """Clears the slot only if it still points at this exact connection --
    if a newer connection already claimed it, this old connection's own
    disconnect must not evict the newer one."""
    if not device_id:
        return
    with _lock:
        if _active.get(device_id) is ws:
            _active.pop(device_id, None)
