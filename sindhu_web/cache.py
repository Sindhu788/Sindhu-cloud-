"""Simple in-memory TTL cache for expensive queries (e.g. COUNT(*) over
millions of candle rows) so the Home/Data pages stay fast on refresh
without hammering the database every poll.

Stale-while-revalidate: once a value has been computed once, an expired
entry is still served immediately while a background thread recomputes it,
instead of blocking the calling request. Without this, a single slow
compute_fn (e.g. COUNT(*) over ~25M rows, which took 60-90s on this
project's database) stalls the HTTP request thread for that entire time on
every cache miss -- and since /api/home is polled by every page's topbar,
that one slow query made the whole app feel hung. Only the very first
call for a given key (no cached value at all yet) blocks synchronously,
since there's nothing else to serve.
"""

import time
import threading

_store = {}
_lock = threading.Lock()
_refreshing = set()


def cached(key, ttl_seconds, compute_fn):
    with _lock:
        entry = _store.get(key)
        now = time.time()
        if entry is not None:
            is_stale = now - entry[0] >= ttl_seconds
            if is_stale and key not in _refreshing:
                _refreshing.add(key)
                threading.Thread(target=_refresh, args=(key, compute_fn), daemon=True).start()
            return entry[1]

    # No cached value yet at all -- nothing to serve, must compute inline.
    value = compute_fn()
    with _lock:
        _store[key] = (now, value)
    return value


def _refresh(key, compute_fn):
    try:
        value = compute_fn()
        with _lock:
            _store[key] = (time.time(), value)
    finally:
        with _lock:
            _refreshing.discard(key)


def cached_nonblocking(key, ttl_seconds, compute_fn, default):
    """Same stale-while-revalidate contract as cached(), except the very
    first call for a key NEVER blocks -- it kicks off the same background
    refresh used for stale entries and returns `default` immediately.

    cached() intentionally blocks on a true first call because most of its
    callers (COUNT queries, JSON reads) finish in well under a second, so
    blocking once is cheaper than plumbing a placeholder through. That
    assumption breaks for genuinely expensive first computations -- e.g.
    disk_usage_bytes() walking the entire data/ tree took 34s+ measured
    here, and stacked with concurrent disk I/O it made /api/home (polled by
    every page's topbar) hang well past a minute on first load after every
    restart. Use this instead of cached() for any compute_fn slow enough
    that no request should ever be the one to pay for it inline."""
    with _lock:
        entry = _store.get(key)
        now = time.time()
        if entry is not None:
            is_stale = now - entry[0] >= ttl_seconds
            if is_stale and key not in _refreshing:
                _refreshing.add(key)
                threading.Thread(target=_refresh, args=(key, compute_fn), daemon=True).start()
            return entry[1]
        if key not in _refreshing:
            _refreshing.add(key)
            threading.Thread(target=_refresh, args=(key, compute_fn), daemon=True).start()
        return default


def invalidate(key):
    with _lock:
        _store.pop(key, None)


def clear_all():
    with _lock:
        _store.clear()
