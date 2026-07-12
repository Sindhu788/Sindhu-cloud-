"""Central logging: every message goes to the console, to a log file under
data/logs/, and to any subscribers (the dashboard's live log window)."""

import threading
from datetime import datetime, timezone

from data_engine.paths import LOG_FILE, ensure_folders

_lock = threading.Lock()
_subscribers = []


def subscribe(callback):
    """Register callback(line: str), invoked for every log line."""
    _subscribers.append(callback)


def unsubscribe(callback):
    if callback in _subscribers:
        _subscribers.remove(callback)


def log(message):
    ensure_folders()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {message}"
    with _lock:
        print(line)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    for cb in list(_subscribers):
        try:
            cb(line)
        except Exception:
            pass
    return line
