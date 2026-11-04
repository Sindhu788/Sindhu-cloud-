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


@router.get("/api/ops/why")
def why(coin: Optional[str] = None, strategy: Optional[str] = None, outcome: Optional[str] = None, hours: int = 24, limit: int = 50):
    """Why did / didn't this coin or strategy produce a signal? Newest decisions first, each with the gate that stopped it,
    the data age and the ordered gate results, plus the latest Telegram send/withheld reasons.
    Example: /api/ops/why?coin=BTC&hours=6"""
    from paper_trading import decision_trace
    return decision_trace.query(coin=coin, strategy=strategy, outcome=outcome, hours=hours, limit=limit)


@router.get("/api/ops/why-summary")
def why_summary(hours: int = 24):
    from paper_trading import decision_trace
    return decision_trace.summary(hours=hours)


@router.get("/api/ops/pinger")
def pinger():
    """Proof that an external pinger reaches /health: in-memory counters of this process only (reset on every restart)."""
    from paper_trading import instance_state
    return instance_state.ping_summary()


_TEST_ALERT_COOLDOWN_MIN = 5


@router.post("/api/ops/test-owner-alert")
def test_owner_alert():
    """Owner-triggered ONLY (a button in Settings > Telegram > Private Alerts): sends one short test message to the owner's private
    chat. Rate limited (one per 5 minutes, persisted). Never touches a public channel; never called by the system itself."""
    from datetime import datetime, timezone
    from paper_trading import monitoring, telegram_bot
    if not telegram_bot.load_settings().get("personal_chat_id"):
        return JSONResponse(status_code=400, content={"ok": False, "error": "Save your personal chat id first (Settings > Telegram > Private Alerts)."})
    limiter = monitoring._limiter or monitoring._persistent_limiter()
    if not limiter.allow("test_owner_alert", _TEST_ALERT_COOLDOWN_MIN):
        return JSONResponse(status_code=429, content={"ok": False, "error": f"A test alert was sent less than {_TEST_ALERT_COOLDOWN_MIN} minutes ago. Please wait."})
    res = telegram_bot.send_private_message("[SINDHU test alert] If you can read this, owner alerts reach this chat. "
                                            + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    if res.get("ok"):
        limiter.mark("test_owner_alert")
        return {"ok": True}
    return JSONResponse(status_code=502, content={"ok": False, "error": res.get("error") or "Telegram did not accept the message."})
