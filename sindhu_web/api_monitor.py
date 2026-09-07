"""Grand Master Prompt, Phase 3.11: API Monitor -- total requests, failed
requests, and average response time for THIS app's own API (not the
exchange's API, which ccxt already self-throttles via enableRateLimit and
exposes no queryable remaining-quota anywhere in this codebase).

In-memory only, deliberately -- this is a live "how is the API doing right
now" gauge, not a permanent audit record (that already exists separately:
audit_trail_log). Resets to zero on every restart, which is honest (a
fresh process has made zero requests so far) rather than confusing.
"""
import threading

_lock = threading.Lock()
_state = {"total_requests": 0, "failed_requests": 0, "total_duration_seconds": 0.0}


def record_request(status_code, duration_seconds):
    with _lock:
        _state["total_requests"] += 1
        if status_code >= 400:
            _state["failed_requests"] += 1
        _state["total_duration_seconds"] += duration_seconds


def get_stats():
    with _lock:
        total = _state["total_requests"]
        avg = (_state["total_duration_seconds"] / total) if total else None
        return {
            "total_requests": total,
            "failed_requests": _state["failed_requests"],
            "average_response_time_seconds": round(avg, 4) if avg is not None else None,
        }
