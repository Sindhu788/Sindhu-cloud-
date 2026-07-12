from fastapi import APIRouter

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
