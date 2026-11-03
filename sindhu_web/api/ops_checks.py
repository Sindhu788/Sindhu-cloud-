"""Owner-facing operational checks: warnings banner feed and Local-vs-Cloud settings parity."""
import json
import urllib.request
from typing import Optional

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

from data_engine import config as base_config
from paper_trading import ops_checks, strategy_sync

router = APIRouter()


@router.get("/api/ops/warnings")
def warnings():
    return {"warnings": ops_checks.collect_warnings()}


@router.get("/api/ops/settings-snapshot")
def settings_snapshot():
    return ops_checks.settings_snapshot()


@router.get("/api/ops/settings-snapshot-sync")
def settings_snapshot_sync(x_sindhu_sync_secret: Optional[str] = Header(None)):
    """Cloud side of the parity check. Same X-Sindhu-Sync-Secret gate as /strategy-sync/push."""
    expected = strategy_sync.get_or_create_sync_secret()
    if not x_sindhu_sync_secret or x_sindhu_sync_secret != expected:
        return JSONResponse(content={"ok": False, "error": "invalid or missing sync secret"}, status_code=401)
    return ops_checks.settings_snapshot()


@router.get("/api/ops/settings-parity")
def settings_parity():
    """Local side: fetch the Cloud snapshot (cloud_sync_target.json) and list every key that differs."""
    target = base_config.load_or_seed("cloud_sync_target.json", {"cloud_url": "", "sync_secret": ""})
    url = (target.get("cloud_url") or "").rstrip("/")
    secret = target.get("sync_secret") or strategy_sync.get_or_create_sync_secret()
    if not url or not secret:
        return {"ok": False, "error": "cloud_sync_target.json has no cloud_url - cannot compare"}
    try:
        req = urllib.request.Request(url + "/api/ops/settings-snapshot-sync", headers={"X-Sindhu-Sync-Secret": secret})
        with urllib.request.urlopen(req, timeout=60) as r:
            cloud = json.loads(r.read())
    except Exception as exc:
        return {"ok": False, "error": f"Cloud unreachable or not updated yet ({type(exc).__name__})"}
    return {"ok": True, **ops_checks.diff_snapshots(ops_checks.settings_snapshot(), cloud)}
