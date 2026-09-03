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
    the live dashboard feed). Same shape, different table -- see
    audit_trail_log in data_engine/storage.py."""
    return {
        "audit_trail": storage.list_audit_trail(limit=limit, entity=entity, since_iso=since),
        "total_count": storage.count_audit_trail(),
    }
