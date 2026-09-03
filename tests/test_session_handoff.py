"""Grand Feature Expansion, Phase 4 Feature 20: Session Handoff
Auto-Summary (data_engine/session_handoff.py) -- a narrative "what
happened / what's next" note, distinct from what_changed.summarize_period
(raw counts): this turns those counts into prose and adds a live
"what's next" section from current state, not history."""

from datetime import datetime, timezone

import pytest

from data_engine import config as base_config, session_handoff, storage
from paper_trading import kill_switch


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _epoch():
    return "2000-01-01T00:00:00+00:00"


def test_quiet_period_says_nothing_happened_and_nothing_urgent(test_db):
    result = session_handoff.generate_handoff_summary(_epoch())
    assert result["total_events"] == 0
    assert "Nothing was recorded" in result["text"]
    assert "nothing urgent waiting" in result["text"]
    assert result["next_up_count"] == 0


def test_open_incident_appears_in_whats_next(test_db):
    storage.create_incident("inc1", "Test Incident", "problem", "tester", "high", datetime.now(timezone.utc).isoformat())
    result = session_handoff.generate_handoff_summary(_epoch())
    assert "1 incident still open" in result["text"]
    assert result["next_up_count"] == 1


def test_active_kill_switch_appears_in_whats_next(test_db):
    kill_switch.activate(reason="testing", actor="tester", close_positions=False)
    result = session_handoff.generate_handoff_summary(_epoch())
    assert "kill switch is still ACTIVE" in result["text"]
    assert "testing" in result["text"]


def test_events_produce_a_narrative_whats_happened_line(test_db):
    now_iso = datetime.now(timezone.utc).isoformat()
    storage.record_audit_event("incident", "created", "Incident opened", now_iso)
    storage.record_audit_event("incident", "created", "Incident opened", now_iso)
    result = session_handoff.generate_handoff_summary(_epoch())
    assert result["total_events"] == 2
    assert "What happened:" in result["text"]
    assert "incident was created 2 times" in result["text"]


def test_endpoint_returns_a_handoff_summary(test_db):
    from sindhu_web.api.project_status import session_handoff as session_handoff_endpoint
    result = session_handoff_endpoint(period="all")
    assert "text" in result
    assert "generated_at" in result
