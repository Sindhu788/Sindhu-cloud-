import os
import re
import time
from datetime import datetime, timezone

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
_SERVER_START_ISO = datetime.fromtimestamp(_SERVER_START_TIME, tz=timezone.utc).isoformat()
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
    uses for module_status -- no new tracking mechanism invented.

    Master Task Expansion, Part 6: this endpoint is now ALSO mounted on
    cloud_runtime/app.py (see that file's lifespan) -- evolution_engine.engine
    is deliberately never imported there at all (cloud_runtime's own tests
    assert this: it has no Evolution Engine, no Governor, by design, to
    keep the cloud runner lightweight). Checking CLOUD_MODE here rather than
    unconditionally importing evolution_engine.engine avoids pulling that
    whole module (and its background-thread machinery) into a live cloud
    process just because someone opened a health-check page -- the cloud
    correctly reports zero evolution activity without ever importing it."""
    from sindhu_web.jobs import job_manager
    from paper_trading.engine import engine as paper_engine
    from sindhu_web.security import CLOUD_MODE

    jobs = job_manager.list_jobs()
    running_jobs = [j for j in jobs if j.status == "running"]
    items = [{"name": j.kind, "detail": getattr(j, "label", None) or j.id} for j in running_jobs]
    if paper_engine.is_running():
        items.append({"name": "paper_trading", "detail": "Paper Trading Engine"})
    if not CLOUD_MODE:
        from evolution_engine.engine import engine as evolution_engine
        if evolution_engine.is_running():
            items.append({"name": "evolution", "detail": "Evolution Engine"})
    return items


@router.get("/api/system/api-monitor")
def get_api_monitor():
    """Grand Master Prompt, Phase 3.11. In-memory, since-this-process-
    started counters -- see sindhu_web/api_monitor.py's own docstring for
    why this is deliberately not a permanent record."""
    from sindhu_web import api_monitor
    return api_monitor.get_stats()


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
        # Grand Master Prompt, Phase 3.4 (Render Server Monitor): this
        # process's own last start time -- the exact same value each
        # deployment's own restart_analytics.record_startup() call wrote
        # to server_restart_log at boot.
        "last_restart_at": _SERVER_START_ISO,
    }


def _deployment_name():
    from sindhu_web.security import CLOUD_MODE
    return "cloud" if CLOUD_MODE else "local"


def record_startup():
    """Call exactly once from each deployment's own lifespan (both
    sindhu_web/server.py and cloud_runtime/app.py) -- Grand Master Prompt,
    Phase 3.13 (Restart Analytics). See server_restart_log's own schema
    comment in data_engine/storage.py for the honest scope of what this
    can and cannot tell the CEO."""
    deployment = _deployment_name()
    storage.record_server_restart(deployment, _SERVER_START_ISO)
    _send_restart_notification(deployment)


def _send_restart_notification(deployment):
    """Grand Master Prompt, Phase 3.10 (Server Notification System):
    "server restarted" + "database connected" in one private Telegram
    message, sent exactly once per process start. Same silent-skip-if-
    not-configured contract as paper_trading/status_ping.py -- never
    raises, never sends to the public channel.

    Honest scope: a genuine "server OFFLINE" alert is NOT possible from
    inside this same process (a dead process cannot notify anyone) -- that
    needs an external uptime pinger, already flagged as a CEO action item
    in a prior session (data/checkpoints/master_task_6.json) for the
    /health endpoint. "System recovered" is this same startup message --
    a restart notification IS the recovery signal, there is no separate
    downtime state this process can observe about itself."""
    try:
        from paper_trading import telegram_bot
        from data_engine import db_backend
        db_status = "Postgres (persists across restarts)" if db_backend.IS_POSTGRES else "local SQLite file"
        message = (f"SINDHU {deployment} deployment restarted at {_SERVER_START_ISO}.\n"
                   f"Database: {db_status}.")
        telegram_bot.send_private_message(message)
    except Exception as e:
        log(f"[restart-notification] failed (non-fatal): {e!r}")


@router.get("/api/system/restart-analytics")
def get_restart_analytics():
    """Grand Master Prompt, Phase 3.13. Counts PROCESS STARTS for this
    deployment -- it cannot distinguish a deliberate restart from a crash
    (both look identical from inside the process), and the "gap since
    previous start" figures are the closest honest proxy for downtime
    available without an external watchdog. Real crash detection /
    minute-accurate downtime would need exactly the kind of external
    uptime pinger already flagged in a prior session (data/checkpoints/
    master_task_6.json) for the /health endpoint -- this does not
    duplicate or replace that, it only makes the app's OWN restart
    history visible from inside itself."""
    deployment = _deployment_name()
    restarts = storage.list_server_restarts(deployment=deployment, limit=50)
    gaps = []
    for newer, older in zip(restarts, restarts[1:]):
        try:
            t_new = datetime.fromisoformat(newer["started_at"])
            t_old = datetime.fromisoformat(older["started_at"])
            gaps.append({"between": [older["started_at"], newer["started_at"]],
                         "gap_seconds": round((t_new - t_old).total_seconds())})
        except ValueError:
            continue
    return {
        "deployment": deployment,
        "restart_count": storage.count_server_restarts(deployment=deployment),
        "last_restart_at": _SERVER_START_ISO,
        "recent_restarts": restarts,
        "gaps_between_recent_restarts": gaps,
        "note": ("Counts process starts only -- cannot tell a deliberate restart apart from a "
                 "crash, and a gap here is time between two starts, not confirmed downtime. "
                 "For real crash/downtime detection, use an external uptime monitor."),
    }
