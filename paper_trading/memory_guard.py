"""Memory guard for the 512 MB free plan (Day 4). Watches this process's RSS; above the soft limit it drops optional caches and skips
optional work (candle prefetch, concept memo), above the hard limit it also tells the owner (owner chat only, rate limited) BEFORE the
platform kills the process. It never touches trading logic, gates or data.

Limits (env, MB): SINDHU_MEM_SOFT_MB (default 400), SINDHU_MEM_HARD_MB (default 450). Plan limit on Render free = 512.
"""
import os
import time

SOFT_MB = float(os.environ.get("SINDHU_MEM_SOFT_MB", "400"))
HARD_MB = float(os.environ.get("SINDHU_MEM_HARD_MB", "450"))
ALERT_EVERY_MIN = 120
_last = {"level": "ok", "rss": 0.0, "soft_events": 0, "hard_events": 0, "alert_at": 0.0}


def rss_mb():
    try:
        import psutil
        return psutil.Process().memory_info().rss / 1e6
    except Exception:
        try:
            with open("/proc/self/status", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1]) / 1024.0
        except Exception:
            pass
    return 0.0


def level(rss=None):
    rss = rss_mb() if rss is None else rss
    return "hard" if rss >= HARD_MB else ("soft" if rss >= SOFT_MB else "ok")


_log_state = {"level": "ok", "at": -1e9, "skipped": 0}
import collections as _collections
_history = _collections.deque(maxlen=288)   # master plan V2 PG7: (unix time, rss MB) once per check (~1/min): about 4.8 h


def history():
    return list(_history)


def optional_work_allowed():
    """False once memory is tight: callers skip prefetch and other non-essential work."""
    return level() == "ok"


def status():
    return dict(_last, soft_mb=SOFT_MB, hard_mb=HARD_MB)


def check(log=print, send=None, now=None, rss=None):
    """Called about once a minute from the engine housekeeping. Returns the level. Never raises."""
    try:
        rss = rss_mb() if rss is None else rss
        lv = level(rss)
        _history.append((int(time.time()), round(rss, 1)))
        _last.update(level=lv, rss=round(rss, 1))
        if lv == "ok":
            _log_state.update(level="ok", skipped=0)
            return lv
        # soft or hard: free what can be rebuilt
        try:
            from backtest_engine import concepts
            concepts.memo_enable(False)
        except Exception:
            pass
        _last["soft_events" if lv == "soft" else "hard_events"] += 1
        # master plan V2 R6 (P29): print when the level changes, and otherwise at most every 30 min with the count (was every ~3 min)
        mono = time.monotonic()
        if lv != _log_state["level"] or mono - _log_state["at"] >= 1800:
            extra = f" ({_log_state['skipped']} repeats not printed)" if _log_state["skipped"] else ""
            log(f"[memory-guard] RSS {rss:.0f} MB >= {SOFT_MB if lv == 'soft' else HARD_MB:.0f} MB ({lv}): concept memo dropped, optional work (prefetch) skipped{extra}")
            _log_state.update(level=lv, at=mono, skipped=0)
        else:
            _log_state["skipped"] += 1
        if lv == "hard":
            now = time.time() if now is None else now
            if now - _last["alert_at"] >= ALERT_EVERY_MIN * 60:
                _last["alert_at"] = now
                try:
                    from paper_trading import monitoring
                    (send or monitoring._owner_send)(f"[SINDHU monitor] ALERT: Cloud memory is {rss:.0f} MB of 512 MB. The server may be restarted by the platform. "
                                                     "Optional work has been switched off to avoid it.")
                except Exception:
                    pass
        return lv
    except Exception:
        return "ok"
