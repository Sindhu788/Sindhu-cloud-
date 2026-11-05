"""Master plan A6 / P29 / P40: repeated background-loop errors are logged once per (source, error type) per window (default
10 minutes), with a count of how many were suppressed since. Errors are never hidden: the first one always prints in full, the
next print says "x37 more since 20:14". Thread-safe, in memory, never raises."""
import threading
import time

_lock = threading.Lock()
_seen = {}          # (source, error_type) -> [last_logged_monotonic, suppressed_count, last_logged_wall]


def error_key(exc):
    """Error type plus its first meaningful words, so different failures of one source are not merged into one."""
    name = type(exc).__name__
    text = str(exc)
    for marker in ("SSL SYSCALL error", "timeout expired", "Network is unreachable", "server closed the connection", "database unavailable"):
        if marker in text:
            return f"{name}:{marker}"
    return name


def should_log(source, exc, every=600, now=None):
    """(True, suppressed_since_last) when this error should be printed now; (False, n) otherwise."""
    try:
        now = time.monotonic() if now is None else now
        key = (source, error_key(exc))
        with _lock:
            entry = _seen.get(key)
            if entry is None or now - entry[0] >= every:
                suppressed = entry[1] if entry else 0
                _seen[key] = [now, 0, time.strftime("%H:%M:%S", time.gmtime())]
                return True, suppressed
            entry[1] += 1
            return False, entry[1]
    except Exception:
        return True, 0


def log_error(log, source, exc, every=600):
    """Print `[source] error: <repr>` the first time, then at most once per `every` seconds with the suppressed count."""
    try:
        ok, suppressed = should_log(source, exc, every)
        if ok:
            more = f" (x{suppressed} more of this error suppressed in the last {every // 60} min)" if suppressed else ""
            log(f"[{source}] error: {exc!r}{more}")
    except Exception:
        pass


def backoff_seconds(consecutive_failures, base=30.0, cap=300.0):
    """30 s, 60 s, 120 s, 240 s, 300 s, 300 s ... (consecutive_failures >= 1)."""
    if consecutive_failures <= 0:
        return 0.0
    return min(cap, base * (2 ** (consecutive_failures - 1)))


def reset():
    with _lock:
        _seen.clear()


def maybe_log(log, source, exc, text, every=600):
    """Like log_error, but prints the caller's own original text (so existing log searches keep working) plus the suppressed count."""
    try:
        ok, suppressed = should_log(source, exc, every)
        if ok:
            log(text + (f" (x{suppressed} more of this error suppressed in the last {every // 60} min)" if suppressed else ""))
    except Exception:
        pass
