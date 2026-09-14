from typing import Optional

from fastapi import APIRouter

from data_engine import storage

router = APIRouter()


@router.get("/api/activity")
def get_activity(limit: int = 50):
    return {"activity": storage.list_activity(limit)}


@router.get("/api/audit-trail")
def get_audit_trail(limit: int = 100, entity: Optional[str] = None, since: Optional[str] = None):
    """Grand Feature Expansion, Phase 1 Feature 3: the permanent, never-
    pruned counterpart to /api/activity (which is capped at 500 rows for
    the live dashboard feed). Same shape, different form -- see
    audit_trail_log in data_engine/storage.py."""
    return {
        "audit_trail": storage.list_audit_trail(limit=limit, entity=entity, since_iso=since),
        "total_count": storage.count_audit_trail(),
    }


_SAFETY_GATE_ENTITIES = ("kill_switch", "account_drawdown", "strategy_drawdown_pause")


@router.get("/api/safety-gate-trip-history")
def get_safety_gate_trip_history(limit: int = 30):
    """Grand Master Batch, Phase 4 Item 18: one merged, time-sorted view
    of every real trip/resume across all three safety gates (Kill
    Switch, account-wide Drawdown Protection, per-strategy Drawdown
    Protection) -- each already permanently logged to audit_trail_log
    with a real plain-language reason via sindhu_web.sync.notify(), just
    never surfaced together in one place before. Read-only; changes no
    gate's behavior."""
    rows = []
    for entity in _SAFETY_GATE_ENTITIES:
        rows.extend(storage.list_audit_trail(limit=limit, entity=entity))
    rows.sort(key=lambda r: r["created_at"], reverse=True)
    return {"events": rows[:limit]}
