"""Incident Management System (Grand Feature Expansion, Phase 1 Feature 4):
a structured record for problem -> detection -> root cause -> fix -> test ->
resolution. Distinct from paper_alerts (auto-generated, trading-specific,
ephemeral) and audit_trail_log (a plain event log with no workflow/status).

Every mutation also calls sync.notify() so an incident's creation and each
stage update shows up in the live Activity Feed and the permanent Audit
Trail (Feature 3) automatically -- no separate logging needed here.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from data_engine import storage
from sindhu_web import sync

router = APIRouter()


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


class CreateIncidentRequest(BaseModel):
    title: str
    problem: str
    detected_by: Optional[str] = None
    severity: str = "medium"


@router.post("/api/incidents")
def create_incident(req: CreateIncidentRequest):
    if req.severity not in storage.INCIDENT_VALID_SEVERITIES:
        raise HTTPException(400, f"severity must be one of {storage.INCIDENT_VALID_SEVERITIES}")
    incident_id = uuid.uuid4().hex[:16]
    incident = storage.create_incident(incident_id, req.title, req.problem, req.detected_by, req.severity, _now_iso())
    sync.notify("incident", "created", f"Incident opened ({req.severity}): {req.title}")
    return incident


@router.get("/api/incidents")
def list_incidents(status: Optional[str] = None, limit: int = 100):
    return {"incidents": storage.list_incidents(status=status, limit=limit)}


@router.get("/api/incidents/{incident_id}")
def get_incident(incident_id: str):
    incident = storage.get_incident(incident_id)
    if not incident:
        raise HTTPException(404, "incident not found")
    return incident


class UpdateIncidentRequest(BaseModel):
    root_cause: Optional[str] = None
    fix_description: Optional[str] = None
    fix_reference: Optional[str] = None
    test_description: Optional[str] = None
    status: Optional[str] = None


@router.post("/api/incidents/{incident_id}/update")
def update_incident(incident_id: str, req: UpdateIncidentRequest):
    if not storage.get_incident(incident_id):
        raise HTTPException(404, "incident not found")
    if req.status and req.status not in storage.INCIDENT_VALID_STATUSES:
        raise HTTPException(400, f"status must be one of {storage.INCIDENT_VALID_STATUSES}")
    fields = {k: v for k, v in req.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(400, "no fields to update")
    incident = storage.update_incident(incident_id, _now_iso(), **fields)
    sync.notify("incident", "updated", f"Incident {incident['title']} updated: {', '.join(fields.keys())}")
    return incident


@router.post("/api/incidents/{incident_id}/resolve")
def resolve_incident(incident_id: str):
    incident = storage.get_incident(incident_id)
    if not incident:
        raise HTTPException(404, "incident not found")
    now = _now_iso()
    incident = storage.update_incident(incident_id, now, status="resolved", resolved_at=now)
    sync.notify("incident", "resolved", f"Incident resolved: {incident['title']}")
    return incident
