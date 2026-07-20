from fastapi import APIRouter, Request

from data_engine.logging_setup import log
from sindhu_web import cache, sync

router = APIRouter()


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
