"""Grand Master Batch, Phase 4 Item 18 -- Safety Gate Trip History.

Covers the real gap found: per-strategy Drawdown Protection pauses never
logged to the permanent audit trail (unlike kill switch / account-wide
drawdown, which already did), plus the new merged endpoint that surfaces
all three gates' trip/resume history together.
"""

from datetime import datetime, timezone

from data_engine import storage
from paper_trading import drawdown_guard, kill_switch, account_drawdown_guard
from sindhu_web.api.activity import get_safety_gate_trip_history


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def test_strategy_pause_is_logged_to_audit_trail(test_db):
    storage.set_strategy_paused("strat1", True, "test reason", _now_iso())
    drawdown_guard._log_trip("strat1", "My Strategy", "5 consecutive losses (threshold: 5).")
    events = storage.list_audit_trail(entity="strategy_drawdown_pause")
    assert len(events) == 1
    assert "My Strategy" in events[0]["message"]
    assert events[0]["action"] == "paused"


def test_strategy_resume_is_logged_to_audit_trail(test_db):
    drawdown_guard.resume_strategy("strat1")
    events = storage.list_audit_trail(entity="strategy_drawdown_pause")
    assert len(events) == 1
    assert events[0]["action"] == "resumed"
    assert "strat1" in events[0]["message"]


def test_evaluate_strategy_streak_pause_logs_a_real_trip(test_db):
    from unittest.mock import patch
    with patch.object(drawdown_guard.insights, "compute_streak", return_value={"type": "loss", "count": 10}):
        reason = drawdown_guard.evaluate_strategy("strat1", "My Strategy")
    assert reason is not None
    events = storage.list_audit_trail(entity="strategy_drawdown_pause")
    assert len(events) == 1
    assert "consecutive losses" in events[0]["message"]


def test_merged_trip_history_combines_all_three_gates_sorted(test_db):
    kill_switch.activate(reason="test emergency", close_positions=False)
    account_drawdown_guard.status()  # sanity: module importable/usable
    storage.record_audit_event("account_drawdown", "paused", "account dd test", _now_iso())
    drawdown_guard._log_trip("strat1", "My Strategy", "drawdown test")

    result = get_safety_gate_trip_history(limit=20)
    entities = {e["entity"] for e in result["events"]}
    assert entities == {"kill_switch", "account_drawdown", "strategy_drawdown_pause"}
    # newest-first
    created_ats = [e["created_at"] for e in result["events"]]
    assert created_ats == sorted(created_ats, reverse=True)


def test_merged_trip_history_empty_when_nothing_has_tripped(test_db):
    result = get_safety_gate_trip_history(limit=20)
    assert result["events"] == []
