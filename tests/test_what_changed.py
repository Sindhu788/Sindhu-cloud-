""""What Changed Today" Diff View (Grand Feature Expansion, Phase 3
Feature 15) -- data_engine.what_changed.summarize_period(), a genuine
automatic diff built entirely from audit_trail_log (Phase 1 Feature 3),
distinct from project_status.py's manually-curated changelog.json.
"""

from data_engine import storage, what_changed


def test_no_events_is_honestly_reported_as_zero(test_db):
    result = what_changed.summarize_period("2026-01-01T00:00:00+00:00")
    assert result["total_events"] == 0
    assert result["summary_lines"] == []


def test_groups_and_counts_by_entity_and_action(test_db):
    storage.record_audit_event("paper_trading", "started", "a", "2026-01-01T00:00:00+00:00")
    storage.record_audit_event("paper_trading", "stopped", "b", "2026-01-01T01:00:00+00:00")
    storage.record_audit_event("incident", "created", "c", "2026-01-01T02:00:00+00:00")
    storage.record_audit_event("incident", "created", "d", "2026-01-01T03:00:00+00:00")

    result = what_changed.summarize_period("2026-01-01T00:00:00+00:00")
    assert result["total_events"] == 4
    counts_by_key = {(c["entity"], c["action"]): c["count"] for c in result["counts"]}
    assert counts_by_key[("incident", "created")] == 2
    assert counts_by_key[("paper_trading", "started")] == 1


def test_busiest_entity_action_pair_is_listed_first(test_db):
    storage.record_audit_event("paper_trading", "started", "a", "2026-01-01T00:00:00+00:00")
    for i in range(3):
        storage.record_audit_event("incident", "created", f"c{i}", f"2026-01-01T0{i}:00:00+00:00")

    result = what_changed.summarize_period("2026-01-01T00:00:00+00:00")
    assert "incident" in result["summary_lines"][0]
    assert "3 times" in result["summary_lines"][0]


def test_singular_vs_plural_wording(test_db):
    storage.record_audit_event("paper_trading", "started", "a", "2026-01-01T00:00:00+00:00")
    result = what_changed.summarize_period("2026-01-01T00:00:00+00:00")
    assert "1 time" in result["summary_lines"][0]
    assert "1 times" not in result["summary_lines"][0]


def test_respects_since_and_until_boundaries(test_db):
    storage.record_audit_event("paper_trading", "started", "a", "2026-01-01T00:00:00+00:00")
    storage.record_audit_event("paper_trading", "started", "b", "2026-01-05T00:00:00+00:00")

    result = what_changed.summarize_period("2026-01-02T00:00:00+00:00")
    assert result["total_events"] == 1

    result = what_changed.summarize_period("2026-01-01T00:00:00+00:00", until_iso="2026-01-02T00:00:00+00:00")
    assert result["total_events"] == 1


def test_recent_events_included_for_drill_down(test_db):
    storage.record_audit_event("kill_switch", "activated", "emergency stop", "2026-01-01T00:00:00+00:00")
    result = what_changed.summarize_period("2026-01-01T00:00:00+00:00")
    assert len(result["recent_events"]) == 1
    assert result["recent_events"][0]["message"] == "emergency stop"
