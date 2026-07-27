import os
import re
import time

import psutil
from fastapi import APIRouter, Request

from data_engine import storage
from data_engine.logging_setup import log
from data_engine.paths import LOG_FILE
from sindhu_web import cache, sync

router = APIRouter()

# System Health Dashboard (System Reliability Group, item 7): stamped at
# import time, which happens once when the server process starts (system.py
# is imported by sindhu_web/server.py's router registration) -- a close
# enough proxy for "server start time" without needing a dedicated startup
# hook.
_SERVER_START_TIME = time.time()
_ERROR_LINE_RE = re.compile(r"error|exception|traceback|failed", re.IGNORECASE)


@router.post("/api/system/restart-services")
def restart_services():
    """"Restart Services" quick action. This is a soft reset (clears every
    in-memory cache so the next request recomputes fresh data) -- it does
    NOT kill/restart the server process itself, since that's not something
    a dashboard button should do unsupervised on a live trading tool."""
    cache.clear_all()
    sync.notify("system", "restarted", "Services soft-restarted (caches cleared)")
    return {"ok": True}


@router.post("/api/system/client-diagnostics")
def client_diagnostics(payload: dict, request: Request):
    """Fire-and-forget beacon app.js sends once per page load (see
    connectWs() in app.js) -- purely diagnostic, writes one line to
    sindhu.log with the ACTUAL viewport width/UA the browser reports.
    Added to close the loop on "mobile CSS isn't showing on my real
    phone" reports: every prior check (file contents, server delivery,
    cache-busting, media-query behavior) can only be verified against a
    simulated viewport in this environment -- this line is the one source
    of truth for what a REAL device actually reports, the next time
    someone opens the dashboard on it. Never raises on a malformed
    payload; this must never be able to break page load."""
    width = payload.get("innerWidth")
    height = payload.get("innerHeight")
    dpr = payload.get("devicePixelRatio")
    ua = str(payload.get("userAgent") or "")[:200]
    log(f"CLIENT DIAGNOSTICS: ip={request.client.host if request.client else '?'} "
        f"viewport={width}x{height} dpr={dpr} ua=\"{ua}\"")
    return {"ok": True}


def _recent_errors(limit=10, tail_bytes=200_000):
    """Last `limit` log lines that look like an error, newest first. Only
    reads the tail of the file (not the whole thing -- sindhu.log grows
    without bound over a long-running deployment) so this stays cheap
    regardless of how old the deployment is."""
    if not os.path.isfile(LOG_FILE):
        return []
    try:
        size = os.path.getsize(LOG_FILE)
        with open(LOG_FILE, "rb") as f:
            f.seek(max(0, size - tail_bytes))
            chunk = f.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    lines = [ln for ln in chunk.splitlines() if _ERROR_LINE_RE.search(ln)]
    return list(reversed(lines[-limit:]))


def _active_background_processes():
    """Plain-language count of what's actually running right now, reusing
    the same per-engine is_running()/list_jobs() calls /api/home already
    uses for module_status -- no new tracking mechanism invented."""
    from sindhu_web.jobs import job_manager
    from paper_trading.engine import engine as paper_engine
    from evolution_engine.engine import engine as evolution_engine

    jobs = job_manager.list_jobs()
    running_jobs = [j for j in jobs if j.status == "running"]
    items = [{"name": j.kind, "detail": getattr(j, "label", None) or j.id} for j in running_jobs]
    if paper_engine.is_running():
        items.append({"name": "paper_trading", "detail": "Paper Trading Engine"})
    if evolution_engine.is_running():
        items.append({"name": "evolution", "detail": "Evolution Engine"})
    return items


@router.get("/api/system/health")
def get_system_health():
    """Live system health at a glance -- auto-refreshed by the dashboard
    (no manual request needed each time), same cheap psutil calls
    /api/home already makes for cpu/ram."""
    uptime_seconds = time.time() - _SERVER_START_TIME
    active = _active_background_processes()
    return {
        "uptime_seconds": round(uptime_seconds),
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "ram_percent": psutil.virtual_memory().percent,
        "database_size_bytes": storage.db_file_size_bytes(),
        "active_background_processes": active,
        "active_process_count": len(active),
        "recent_errors": _recent_errors(),
    }
