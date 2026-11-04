"""In-memory facts about THIS process: when it started and who has been pinging /health. No database, no network, no files.

Why: the Render free plan stops the process after ~15 min without an inbound request and starts a NEW process on the next one
(a new instance id each time). Monitoring must tell "just woke up / was asleep" apart from "running but not scanning", and the
owner needs proof that the external pinger (cron-job.org / UptimeRobot) really reaches the service.
"""
import threading
import time

PROCESS_STARTED_AT = time.time()
WAKE_GRACE_SECONDS = 600           # after a (re)start the scanner/stale-data alerts stay quiet this long
PINGER_MAX_GAP_SECONDS = 360       # pings closer together than this (on average) count as "an active pinger"
_lock = threading.Lock()
_pings = []                        # recent (timestamp, source) of inbound /health requests, newest last, max 50


def classify_source(user_agent):
    """'render' = Render's own health probe (it does NOT keep a free service awake), else 'external'. Heuristic on User-Agent."""
    return "render" if "render" in (user_agent or "").lower() else "external"


def note_health_ping(user_agent=None, now=None):
    now = time.time() if now is None else now
    with _lock:
        _pings.append((now, classify_source(user_agent)))
        del _pings[:-50]


def ping_summary(now=None):
    now = time.time() if now is None else now
    with _lock:
        pings = list(_pings)
    ext = [t for t, s in pings if s == "external"]
    last_ext = ext[-1] if ext else None
    recent = [t for t in ext if now - t <= 1800]
    avg_gap = None
    if len(recent) >= 3:
        gaps = [b - a for a, b in zip(recent, recent[1:])]
        avg_gap = sum(gaps) / len(gaps)
    return {
        "external_pings_seen": len(ext),
        "seconds_since_last_external_ping": None if last_ext is None else round(now - last_ext, 1),
        "seconds_since_last_render_probe": next((round(now - t, 1) for t, s in reversed(pings) if s == "render"), None),
        "average_gap_seconds": None if avg_gap is None else round(avg_gap, 1),
        "pinger_active": bool(avg_gap is not None and avg_gap <= PINGER_MAX_GAP_SECONDS and last_ext is not None and now - last_ext <= PINGER_MAX_GAP_SECONDS * 2),
        "process_age_seconds": round(now - PROCESS_STARTED_AT, 1),
    }


def in_wake_grace(now=None):
    now = time.time() if now is None else now
    return now - PROCESS_STARTED_AT < WAKE_GRACE_SECONDS
