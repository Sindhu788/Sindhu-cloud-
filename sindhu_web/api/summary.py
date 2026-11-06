"""Master plan A19 (P10): ONE light, cached summary for the home page instead of ~25 separate calls.
Cached 30 s; while one request computes it, others get the previous copy (single flight). Reads in-memory engine state plus a few cheap
queries (MAIN_WALLET), never per-strategy history. Paper only."""
import threading
import time

from fastapi import APIRouter

router = APIRouter()
_TTL_S = 30
_cache = {"at": 0.0, "data": None}
_lock = threading.Lock()


def _next_tick(engine):
    """last tick + tick_interval_seconds (master plan V2 PG2 "next scan in"); None when the engine is not running."""
    try:
        from datetime import datetime, timedelta
        from paper_trading import config as pt_config
        last = getattr(engine, "_last_tick_at", None)
        if not last or not getattr(engine, "_running", False):
            return None
        return (datetime.fromisoformat(last) + timedelta(seconds=pt_config.load().get("tick_interval_seconds", 60))).isoformat()
    except Exception:
        return None


def _compute():
    out = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "paper_only": True}
    try:
        from paper_trading import wallet
        out["wallet"] = wallet.summary()
        out["wallet"]["last_events"] = wallet.journal(5)
    except Exception as e:
        out["wallet"] = {"error": type(e).__name__}
    try:
        from paper_trading.engine import engine
        prog = dict(getattr(engine, "_scan_progress", {}) or {})
        out["engine"] = {"running": bool(getattr(engine, "_running", False)), "scan_in_progress": bool(prog.get("in_progress")),
                         "scan_index": prog.get("index"), "scan_total": prog.get("total"),
                         "last_summary": getattr(engine, "_last_summary", None),
                         "last_tick_seconds": getattr(engine, "_last_tick_duration_seconds", None),
                         "last_tick_at": getattr(engine, "_last_tick_at", None), "next_tick_at": _next_tick(engine)}
    except Exception as e:
        out["engine"] = {"error": type(e).__name__}
    try:
        from paper_trading import kill_switch
        out["kill_switch"] = kill_switch.status()
    except Exception:
        out["kill_switch"] = None
    try:
        from paper_trading import self_check
        d = self_check.details()
        out["system"] = {"trading": d["trading"], "candles": d.get("candles"), "db_breaker": d.get("db_breaker"),
                         "self_check_ok": (d.get("self_check") or {}).get("ok")}
    except Exception:
        out["system"] = None
    return out


@router.get("/api/summary")
def get_summary(refresh: bool = False):
    now = time.time()
    if not refresh and _cache["data"] is not None and now - _cache["at"] < _TTL_S:
        return {**_cache["data"], "cached": True, "age_s": round(now - _cache["at"], 1)}
    if not _lock.acquire(blocking=_cache["data"] is None):
        return {**_cache["data"], "cached": True, "age_s": round(now - _cache["at"], 1)}
    try:
        data = _compute()
        _cache.update(at=time.time(), data=data)
        return {**data, "cached": False, "age_s": 0.0}
    finally:
        _lock.release()
