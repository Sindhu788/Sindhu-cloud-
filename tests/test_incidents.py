"""Grand Feature Expansion, Phase 1 Feature 4: Incident Management System
-- a structured problem -> detection -> root cause -> fix -> test ->
resolution record (data_engine/storage.py's incidents table +
sindhu_web/api/incidents.py). Confirms the workflow end to end, that
nothing is ever deleted, and that every mutation reaches the Audit Trail
(Feature 3) automatically via sync.notify().
"""

import pytest
from fastapi import HTTPException

from data_engine import storage
from sindhu_web.api import incidents as incidents_api


def test_create_incident_defaults_to_open_status(test_db):
    incident = incidents_api.create_incident(
        incidents_api.CreateIncidentRequest(title="Engine crashed", problem="NPE on tick", severity="high")
    )
    assert incident["status"] == "open"
    assert incident["severity"] == "high"
    assert incident["root_cause"] is None
    assert incident["resolved_at"] is None


def test_create_incident_rejects_an_invalid_severity(test_db):
    with pytest.raises(HTTPException) as exc:
        incidents_api.create_incident(
            incidents_api.CreateIncidentRequest(title="x", problem="y", severity="catastrophic")
        )
    assert exc.value.status_code == 400


def test_full_workflow_root_cause_fix_test_resolve(test_db):
    incident = incidents_api.create_incident(
        incidents_api.CreateIncidentRequest(title="Telegram silent", problem="No signals sent for 2 days")
    )
    incident_id = incident["id"]

    updated = incidents_api.update_incident(incident_id, incidents_api.UpdateIncidentRequest(
        root_cause="rate limiter stuck at max", status="root_cause_found",
    ))
    assert updated["root_cause"] == "rate limiter stuck at max"
    assert updated["status"] == "root_cause_found"

    updated = incidents_api.update_incident(incident_id, incidents_api.UpdateIncidentRequest(
        fix_description="reset hourly counter on settings reload", fix_reference="commit abc123",
        status="fixed",
    ))
    assert updated["fix_description"] == "reset hourly counter on settings reload"
    assert updated["status"] == "fixed"

    updated = incidents_api.update_incident(incident_id, incidents_api.UpdateIncidentRequest(
        test_description="sent 5 test signals, all delivered",
    ))
    assert updated["test_description"] == "sent 5 test signals, all delivered"
    # A field not touched by this update call must survive untouched.
    assert updated["root_cause"] == "rate limiter stuck at max"

    resolved = incidents_api.resolve_incident(incident_id)
    assert resolved["status"] == "resolved"
    assert resolved["resolved_at"] is not None


def test_update_rejects_an_invalid_status(test_db):
    incident = incidents_api.create_incident(
        incidents_api.CreateIncidentRequest(title="x", problem="y")
    )
    with pytest.raises(HTTPException) as exc:
        incidents_api.update_incident(incident["id"], incidents_api.UpdateIncidentRequest(status="not_a_real_status"))
    assert exc.value.status_code == 400


def test_get_and_update_unknown_incident_raise_404(test_db):
    with pytest.raises(HTTPException) as exc:
        incidents_api.get_incident("does-not-exist")
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as exc:
        incidents_api.update_incident("does-not-exist", incidents_api.UpdateIncidentRequest(status="fixed"))
    assert exc.value.status_code == 404


def test_list_incidents_filters_by_status(test_db):
    incidents_api.create_incident(incidents_api.CreateIncidentRequest(title="a", problem="a"))
    b = incidents_api.create_incident(incidents_api.CreateIncidentRequest(title="b", problem="b"))
    incidents_api.resolve_incident(b["id"])

    all_incidents = incidents_api.list_incidents()["incidents"]
    assert len(all_incidents) == 2
    open_only = incidents_api.list_incidents(status="open")["incidents"]
    assert len(open_only) == 1
    assert open_only[0]["title"] == "a"


def test_nothing_is_ever_deleted(test_db):
    incident = incidents_api.create_incident(incidents_api.CreateIncidentRequest(title="a", problem="a"))
    incidents_api.resolve_incident(incident["id"])
    # Resolved incidents remain fully readable, not archived away.
    assert storage.get_incident(incident["id"])["status"] == "resolved"
    import inspect
    assert "DELETE" not in inspect.getsource(storage.update_incident)
    assert "DELETE" not in inspect.getsource(storage.create_incident)


def test_every_mutation_reaches_the_permanent_audit_trail(test_db):
    incident = incidents_api.create_incident(incidents_api.CreateIncidentRequest(title="a", problem="a"))
    incidents_api.update_incident(incident["id"], incidents_api.UpdateIncidentRequest(root_cause="x"))
    incidents_api.resolve_incident(incident["id"])

    audit = storage.list_audit_trail(entity="incident")
    actions = {r["action"] for r in audit}
    assert actions == {"created", "updated", "resolved"}
