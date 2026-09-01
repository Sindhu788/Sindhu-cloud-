"""Item 10 (Parser & Extraction Improvements) -- User Correction Learning.

CRITICAL SAFETY CONSTRAINT from the task spec: must never silently assume
an answer on a materially different case, must only suppress a question
where the pattern match is unambiguous, and must remain fully auditable
with an override. These tests exercise exactly those boundaries: a real
consistent pattern gets learned and applied with a visible audit note; an
inconsistent history, a single-strategy repeat, or a safety-critical field
never gets auto-applied."""

from ai_integration import correction_learning, self_correction
from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from backtest_engine import strategy_library as lib
from sindhu_web.api import clarification as clar_api


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(correction_learning, "_HISTORY_PATH", str(tmp_path / "correction_history.json"))


def test_no_suggestion_below_the_consistency_window(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    correction_learning.record_resolution("risk_pct", 1.0, "strat-a")
    correction_learning.record_resolution("risk_pct", 1.0, "strat-b")
    assert correction_learning.learned_suggestion("risk_pct") is None  # only 2 so far, window is 3


def test_consistent_answer_across_distinct_strategies_is_learned(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    for sid in ("strat-a", "strat-b", "strat-c"):
        correction_learning.record_resolution("risk_pct", 1.0, sid)
    result = correction_learning.learned_suggestion("risk_pct")
    assert result == {"value": 1.0, "based_on": 3}


def test_inconsistent_answers_are_never_learned(tmp_path, monkeypatch):
    """Safety: a mixed history must never be collapsed into a guess."""
    _isolate(tmp_path, monkeypatch)
    correction_learning.record_resolution("risk_pct", 1.0, "strat-a")
    correction_learning.record_resolution("risk_pct", 2.0, "strat-b")
    correction_learning.record_resolution("risk_pct", 1.0, "strat-c")
    assert correction_learning.learned_suggestion("risk_pct") is None


def test_one_strategy_edited_repeatedly_is_not_a_pattern(tmp_path, monkeypatch):
    """Safety: 3 edits of the SAME strategy is not a repeated pattern
    across different documents -- must not be learned."""
    _isolate(tmp_path, monkeypatch)
    for _ in range(3):
        correction_learning.record_resolution("risk_pct", 1.0, "strat-a")
    assert correction_learning.learned_suggestion("risk_pct") is None


def test_stop_loss_is_never_an_eligible_field(tmp_path, monkeypatch):
    """Safety-critical field: never learned, regardless of history."""
    _isolate(tmp_path, monkeypatch)
    for sid in ("strat-a", "strat-b", "strat-c"):
        correction_learning.record_resolution("stop_loss", {"type": "fixed_pct", "value": 1.0}, sid)
    assert correction_learning.learned_suggestion("stop_loss") is None
    data = correction_learning._read()
    assert "stop_loss" not in data  # never even recorded


def test_apply_learned_corrections_fills_missing_entry_timeframe(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    for sid in ("strat-a", "strat-b", "strat-c"):
        correction_learning.record_resolution("entry_timeframe", "1h", sid)

    cfg = StrategyConfig(name="Test", raw_text="", timeframes={},
                          entry_conditions=[Condition(type="indicator_compare", indicator="rsi", op="<", value=30.0)],
                          stop_loss=SLTPSpec(type="fixed_pct", value=1.0), risk_pct=1.0)
    applied = correction_learning.apply_learned_corrections(cfg)
    assert cfg.timeframes["entry"] == "1h"
    assert applied == [{"field": "entry_timeframe", "value": "1h", "based_on": 3}]


def test_apply_learned_corrections_never_touches_an_already_valid_field(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    for sid in ("strat-a", "strat-b", "strat-c"):
        correction_learning.record_resolution("risk_pct", 1.0, sid)

    cfg = StrategyConfig(name="Test", raw_text="", timeframes={"entry": "5m"},
                          entry_conditions=[Condition(type="indicator_compare", indicator="rsi", op="<", value=30.0)],
                          stop_loss=SLTPSpec(type="fixed_pct", value=1.0), risk_pct=2.5)  # already valid, different value
    applied = correction_learning.apply_learned_corrections(cfg)
    assert cfg.risk_pct == 2.5  # untouched -- was never missing/invalid
    assert applied == []


def test_self_correction_auto_repair_applies_and_reports_the_learned_field(tmp_path, monkeypatch):
    """The audit-trail proof: self_correction.auto_repair (Level 1, run on
    every import) applies the learned value AND returns a human-readable
    note explaining why -- never a silent mutation."""
    _isolate(tmp_path, monkeypatch)
    for sid in ("strat-a", "strat-b", "strat-c"):
        correction_learning.record_resolution("risk_pct", 1.5, sid)

    cfg = StrategyConfig(name="Test", raw_text="", timeframes={"entry": "5m"},
                          entry_conditions=[Condition(type="indicator_compare", indicator="rsi", op="<", value=30.0)],
                          exit_conditions=[], stop_loss=SLTPSpec(type="fixed_pct", value=1.0), risk_pct=None)
    repairs = self_correction.auto_repair(cfg)
    assert cfg.risk_pct == 1.5
    assert any("risk_pct" in r and "3 times before" in r for r in repairs)


def test_clarify_endpoint_records_the_resolution_for_future_learning(test_db, tmp_path, monkeypatch):
    """End-to-end write side: resolving a real missing-field clarification
    through the actual API records it for the learning history."""
    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path / "library"))
    _isolate(tmp_path, monkeypatch)

    cfg = StrategyConfig(name="Needs Risk Pct", raw_text="test", timeframes={"entry": "5m"},
                          entry_conditions=[Condition(type="indicator_compare", indicator="rsi", op="<", value=30.0)],
                          exit_conditions=[], stop_loss=SLTPSpec(type="fixed_pct", value=1.0), risk_pct=None)
    strategy_id = lib.create(cfg)

    req = clar_api.ClarifyRequest(resolutions=[
        clar_api.ClarifyResolution(id="field:risk_pct", action="set_field", value=1.0),
    ])
    result = clar_api.clarify_strategy(strategy_id, req)
    assert len(result["applied"]) == 1

    history = correction_learning._read()
    assert history["risk_pct"][-1]["value"] == 1.0
    assert history["risk_pct"][-1]["strategy_id"] == strategy_id
