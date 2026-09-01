"""Clarification Page (Step 3, Part B) -- backend tests for the new
endpoints added to sindhu_web/api/clarification.py: the free-text
preview/confirm-back safety endpoint (feature 7), the cross-strategy
aggregate list (feature 5), the Read Mode summary (feature 10), and the
unmark_manual_review edit-previous-answer action (feature 8). The
existing openClarifyBox/build_issues/apply_resolution machinery already
has its own coverage in test_clarification_manual_review.py -- these
tests only cover what's new. Calls endpoint functions directly (same
convention as test_wizard_api.py) rather than an HTTP TestClient, which
this environment doesn't have httpx installed for.
"""

import pytest
from fastapi import HTTPException

from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from backtest_engine import strategy_library as lib
from backtest_engine.validator import validate
from sindhu_web.api import clarification as clar_api, backtesting


def _isolated_library(tmp_path, monkeypatch):
    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path / "library"))


def _make_strategy(**overrides):
    base = dict(
        name="Clarification Page Test Strategy",
        raw_text="test",
        timeframes={"entry": "5m"},
        entry_conditions=[Condition(type="raw", text="enter when the Low Volume Node gets swept")],
        exit_conditions=[Condition(type="concept", name="resistance", direction="bearish")],
        concepts_used=["resistance"],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0),
        take_profit=SLTPSpec(type="rr", value=2.0),
        risk_pct=1.0, risk_reward=2.0,
    )
    base.update(overrides)
    return StrategyConfig(**base)


def test_preview_endpoint_never_mutates_the_strategy(test_db, tmp_path, monkeypatch):
    _isolated_library(tmp_path, monkeypatch)
    strategy_id = lib.create(_make_strategy())
    req = clar_api.ClarifyPreviewRequest(id="entry_conditions:0", text="RSI 14 below 30")
    result = clar_api.preview_clarification_answer(strategy_id, req)
    assert "rsi" in result["understood_as"].lower()
    assert result["still_unclear"] is False
    after = lib.load(strategy_id)
    assert after.entry_conditions[0].type == "raw"  # untouched -- preview never saves


def test_preview_endpoint_reports_still_unclear_for_unmappable_text(test_db, tmp_path, monkeypatch):
    _isolated_library(tmp_path, monkeypatch)
    strategy_id = lib.create(_make_strategy())
    req = clar_api.ClarifyPreviewRequest(id="entry_conditions:0", text="some proprietary indicator nobody has heard of")
    result = clar_api.preview_clarification_answer(strategy_id, req)
    assert result["still_unclear"] is True


def test_aggregate_endpoint_groups_by_strategy(test_db, tmp_path, monkeypatch):
    _isolated_library(tmp_path, monkeypatch)
    s1 = lib.create(_make_strategy(name="Strategy One"))
    s2 = lib.create(_make_strategy(name="Strategy Two"))
    result = clar_api.get_all_pending_clarifications()
    ids = {g["strategy_id"] for g in result["groups"]}
    assert s1 in ids and s2 in ids
    assert result["strategy_count"] == 2
    assert result["total_issues"] >= 2


def test_aggregate_endpoint_excludes_ready_strategies(test_db, tmp_path, monkeypatch):
    _isolated_library(tmp_path, monkeypatch)
    ready = _make_strategy(
        entry_conditions=[Condition(type="concept", name="support", direction="bullish")],
        concepts_used=["resistance", "support"],
    )
    strategy_id = lib.create(ready)
    result = clar_api.get_all_pending_clarifications()
    ids = {g["strategy_id"] for g in result["groups"]}
    assert strategy_id not in ids


def test_read_mode_summary_covers_every_structural_section(test_db, tmp_path, monkeypatch):
    _isolated_library(tmp_path, monkeypatch)
    strategy_id = lib.create(_make_strategy())
    result = clar_api.get_read_mode(strategy_id)
    section_ids = {s["id"] for s in result["sections"]}
    assert {"entry", "exit", "sltp", "risk", "filters", "status"} <= section_ids
    assert result["ready_for_backtest"] is False  # the raw entry condition is still unresolved


def test_read_mode_status_reflects_real_validator_errors_not_just_raw_conditions():
    """Regression test for a bug caught during live browser verification:
    the status section used to only count raw/manual_review conditions,
    so a strategy blocked by a DIFFERENT validator error (e.g. an exit
    concept missing from concepts_used) showed "sab kuch clear hai" (all
    clear) while still genuinely blocked -- misleading even though the
    actual gate (ready_for_backtest) was correct. Fixed to use the same
    validate(cfg) errors the gate itself is computed from."""
    cfg = _make_strategy(
        entry_conditions=[Condition(type="concept", name="support", direction="bullish")],
        concepts_used=[],  # exit condition names "resistance" but it's missing here -- a real, non-raw error
    )
    errors = validate(cfg)
    assert errors  # confirm this scenario really is blocked
    sections = clar_api._read_mode_summary(cfg, errors)
    status_text = next(s["text"] for s in sections if s["id"] == "status")
    assert "sab kuch clear hai" not in status_text.lower()


def test_unmark_manual_review_reopens_a_previously_answered_question(test_db, tmp_path, monkeypatch):
    _isolated_library(tmp_path, monkeypatch)
    strategy_id = lib.create(_make_strategy())
    clar_api.clarify_strategy(strategy_id, clar_api.ClarifyRequest(resolutions=[
        clar_api.ClarifyResolution(id="entry_conditions:0", action="mark_manual_review"),
    ]))
    cfg = lib.load(strategy_id)
    assert cfg.entry_conditions[0].manual_review is True

    result = clar_api.clarify_strategy(strategy_id, clar_api.ClarifyRequest(resolutions=[
        clar_api.ClarifyResolution(id="entry_conditions:0", action="unmark_manual_review"),
    ]))
    assert result["applied"]
    cfg_after = lib.load(strategy_id)
    assert cfg_after.entry_conditions[0].manual_review is False


def test_answer_log_is_returned_and_records_the_action(test_db, tmp_path, monkeypatch):
    _isolated_library(tmp_path, monkeypatch)
    # A strategy with a SECOND, still-unresolved issue (missing concepts_used
    # entry) so the strategy stays NEEDS_CLARIFICATION after resolving the
    # first one -- the answer log is only kept while that's true (once fully
    # resolved it's intentionally cleared, see clarify_strategy), so a
    # strategy that fully resolves after one answer isn't the right fixture
    # to prove the log persisted.
    strategy_id = lib.create(_make_strategy(concepts_used=[]))
    clar_api.clarify_strategy(strategy_id, clar_api.ClarifyRequest(resolutions=[
        clar_api.ClarifyResolution(id="entry_conditions:0", action="mark_manual_review"),
    ]))
    result = clar_api.get_clarification(strategy_id)
    assert result["status"] == "NEEDS_CLARIFICATION"
    log = result["answer_log"]
    assert len(log) == 1
    assert log[0]["action"] == "mark_manual_review"


def test_incomplete_lock_still_blocks_a_strategy_with_manual_review_condition(test_db, tmp_path, monkeypatch):
    """Confirms the Clarification Page changes did not weaken the
    Incomplete Lock: a strategy with an unresolved manual_review condition
    still gets HTTP 423 from the real run endpoint, exactly as before."""
    _isolated_library(tmp_path, monkeypatch)
    strategy_id = lib.create(_make_strategy(
        entry_conditions=[Condition(type="raw", text="proprietary signal", manual_review=True, raw_source="proprietary signal")],
    ))
    req = backtesting.RunRequest(strategy_id=strategy_id, all_coins=False, symbols=["BTCUSDT"])
    with pytest.raises(HTTPException) as exc_info:
        backtesting.run_backtest(req)
    assert exc_info.value.status_code == 423
