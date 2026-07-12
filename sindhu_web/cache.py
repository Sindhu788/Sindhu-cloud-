"""Simple in-memory TTL cache for expensive queries (e.g. COUNT(*) over
millions of candle rows) so the Home/Data pages stay fast on refresh
without hammering the database every poll."""

import time
import threading

_store = {}
_lock = threading.Lock()


def cached(key, ttl_seconds, compute_fn):
    with _lock:
        entry = _store.get(key)
        now = time.time()
        if entry and now - entry[0] < ttl_seconds:
            return entry[1]

    value = compute_fn()
    with _lock:
        _store[key] = (now, value)
    return value


def invalidate(key):
    with _lock:
        _store.pop(key, None)


def clear_all():
    with _lock:
        _store.clear()
