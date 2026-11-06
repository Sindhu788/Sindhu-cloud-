"""Master plan V2 R6 (P29): count log lines per hour and drop the repetitive uvicorn lines.

- Successful GET/HEAD access lines (dashboard polling, static files, /health pings) are not printed. Every 4xx/5xx line and every
  non-GET request (logins, settings saves, kill-switch) is still printed. `SINDHU_ACCESS_LOG=all` prints everything again.
- WebSocket "connection open/closed" and "[accepted]" lines are not printed (the live-log page reconnects often).
- Every line written to stdout/stderr (print, logging, uvicorn) is counted in hourly buckets: /health/details "log_lines".
Errors are never filtered: only INFO-level uvicorn records match the rules above."""
import logging
import os
import sys
import threading
import time

_lock = threading.Lock()
_buckets = {}            # hour start (epoch s) -> lines
_KEEP_HOURS = 48
_filtered = {"access_2xx_get": 0, "websocket": 0}
_installed = {"done": False}


def _note(n):
    if n <= 0:
        return
    h = int(time.time() // 3600 * 3600)
    with _lock:
        _buckets[h] = _buckets.get(h, 0) + n
        if len(_buckets) > _KEEP_HOURS:
            for k in sorted(_buckets)[:-_KEEP_HOURS]:
                del _buckets[k]


class _CountingStream:
    def __init__(self, inner):
        self._inner = inner

    def write(self, s):
        try:
            _note(s.count("\n"))
        except Exception:
            pass
        return self._inner.write(s)

    def __getattr__(self, name):
        return getattr(self._inner, name)


class _AccessFilter(logging.Filter):
    def filter(self, record):
        try:
            if record.levelno > logging.INFO:
                return True
            args = record.args if isinstance(record.args, tuple) else ()
            if len(args) >= 5:
                method, status = str(args[1]).upper(), int(args[4])
                if method in ("GET", "HEAD") and status < 400:
                    _filtered["access_2xx_get"] += 1
                    return False
            return True
        except Exception:
            return True


class _WebsocketNoiseFilter(logging.Filter):
    def filter(self, record):
        try:
            if record.levelno > logging.INFO:
                return True
            msg = record.getMessage()
            if msg in ("connection open", "connection closed") or msg.endswith("[accepted]"):
                _filtered["websocket"] += 1
                return False
            return True
        except Exception:
            return True


def install():
    """Idempotent. Called at Cloud app import (uvicorn has configured its loggers by then)."""
    if _installed["done"]:
        return
    _installed["done"] = True
    try:
        if not isinstance(sys.stdout, _CountingStream):
            sys.stdout = _CountingStream(sys.stdout)
        if not isinstance(sys.stderr, _CountingStream):
            sys.stderr = _CountingStream(sys.stderr)
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access", ""):
            for h in logging.getLogger(name).handlers:
                if isinstance(h, logging.StreamHandler) and not isinstance(h.stream, _CountingStream):
                    h.setStream(_CountingStream(h.stream))
        if (os.environ.get("SINDHU_ACCESS_LOG") or "").strip().lower() != "all":
            logging.getLogger("uvicorn.access").addFilter(_AccessFilter())
            logging.getLogger("uvicorn.error").addFilter(_WebsocketNoiseFilter())
    except Exception:
        pass


def stats(now=None):
    now = time.time() if now is None else now
    cur = int(now // 3600 * 3600)
    with _lock:
        b = dict(_buckets)
    hours = sorted(b)
    return {"this_hour": b.get(cur, 0), "last_full_hour": b.get(cur - 3600),
            "per_hour": [{"hour_utc": time.strftime("%Y-%m-%dT%H:00Z", time.gmtime(h)), "lines": b[h]} for h in hours[-24:]],
            "not_printed": dict(_filtered)}
