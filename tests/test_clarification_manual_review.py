"""Batch 11, Task 5 -- the clarification flow's one-click "suggested
default" (mark_manual_review): accepting the default resolves the
clarification issue (Condition.is_unclear() / validate() stop flagging it)
without guessing a structured meaning for it, but the strategy still can't
actually backtest until a human really resolves it -- the same
manual-review run-time gate the Strategy Wizard's "Other/bilkul naya" path
already uses stays in force."""

import pytest
from fastapi import HTTPException

from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from backtest_engine.strategy_parser import parse_strategy_text
from backtest_engine.validator import validate
from backtest_engine import strategy_library as lib, wizard
from sindhu_web.api import clarification, backtesting


def _isolated_library(tmp_path, monkeypatch):
    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path / "library"))


def test_manual_review_condition_is_no_longer_unclear():
    cond = Condition(type="raw", text="fail to make lower low")
    assert cond.is_unclear() is True
    cond.manual_review = True
    assert cond.is_unclear() is False


def test_validate_stops_flagging_a_manual_review_condition():
    cfg = StrategyConfig(
        name="Test", timeframes={"entry": "1m"},
        entry_conditions=[
            Condition(type="concept", name="fvg", direction="bullish"),
            Condition(type="raw", text="fail to make lower low"),
        ],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0),
        take_profit=SLTPSpec(type="rr", value=2.0),
        risk_pct=1.0,
    )
    errors_before = validate(cfg)
    assert any("fail to make lower low" in e for e in errors_before)

    cfg.entry_conditions[1].manual_review = True
    errors_after = validate(cfg)
    assert not any("fail to make lower low" in e for e in errors_after)


def test_apply_resolution_mark_manual_review():
    cfg = StrategyConfig(
        name="Test", entry_conditions=[Condition(type="raw", text="bullish displacement")],
    )
    ok, detail = clarification._apply_resolution(cfg, "entry_conditions:0", "mark_manual_review", None, None)
    assert ok is True
    cond = cfg.entry_conditions[0]
    assert cond.manual_review is True
    assert cond.raw_source == "bullish displacement"
    assert cond.text == "bullish displacement"  # original text preserved verbatim, never rewritten


def test_apply_resolution_mark_manual_review_rejects_non_raw_condition():
    cfg = StrategyConfig(name="Test", entry_conditions=[Condition(type="concept", name="fvg")])
    ok, detail = clarification._apply_resolution(cfg, "entry_conditions:0", "mark_manual_review", None, None)
    assert ok is False


def test_apply_resolution_mark_manual_review_rejects_missing_conditions_issue():
    cfg = StrategyConfig(name="Test")
    ok, detail = clarification._apply_resolution(cfg, "entry_conditions:new", "mark_manual_review", None, None)
    assert ok is False


# ------------------------------------------------------------- real evidence: the 6 unclear items from the HTF FVG doc

_REAL_HTF_FVG_DOC = """Long setup: reject bullish HTF FVG, fail to make lower low, bullish ChoCH, bullish displacement, bullish 1m FVG, long entry
Short setup: reject bearish HTF FVG, fail to make higher high, bearish ChoCH, bearish displacement, bearish 1m FVG, short entry

Entry timeframe: 1m
Stop loss: fixed 0.3%
Take profit: RR 4
Risk percent: 1
"""


def test_build_issues_surfaces_the_real_unclear_items_as_raw_condition_issues():
    """Regression test for a real bug found while building this feature:
    build_issues() only ever searched entry_conditions for a match, but
    validator.py's "Unclear entry rule" message doesn't say WHICH of the
    three entry buckets (entry_conditions / long_entry_conditions /
    short_entry_conditions -- Batch 6's per-direction rule sets) the
    condition actually lives in. A mixed long/short document like this one
    (which routes entirely into long/short_entry_conditions, leaving
    entry_conditions empty) had every one of its unclear rules silently
    never surfaced as a fixable clarification issue at all."""
    cfg = parse_strategy_text(_REAL_HTF_FVG_DOC, "HTF FVG Reversal Strategy")
    assert cfg.entry_conditions == []
    assert len(cfg.long_entry_conditions) == 6 and len(cfg.short_entry_conditions) == 6

    issues = clarification.build_issues(cfg)
    raw_issues = [i for i in issues if i["kind"] == "raw_condition"]
    original_texts = {i["original_text"] for i in raw_issues}
    # the exact 6 genuinely-unclear phrases from today's real test document
    assert "fail to make lower low" in original_texts
    assert "bullish displacement" in original_texts
    assert "long entry" in original_texts
    assert "fail to make higher high" in original_texts
    assert "bearish displacement" in original_texts
    assert "short entry" in original_texts
    assert len(raw_issues) == 6
    assert all(i["section"] in ("long_entry_conditions", "short_entry_conditions") for i in raw_issues)


def test_accepting_the_default_on_all_six_resolves_clarification_but_run_stays_blocked(test_db, tmp_path, monkeypatch):
    _isolated_library(tmp_path, monkeypatch)
    cfg = parse_strategy_text(_REAL_HTF_FVG_DOC, "HTF FVG Reversal Strategy")
    strategy_id = lib.create(cfg)

    issues = clarification.build_issues(cfg)
    raw_issues = [i for i in issues if i["kind"] == "raw_condition"]
    assert len(raw_issues) == 6

    resolutions = [
        clarification.ClarifyResolution(id=i["id"], action="mark_manual_review")
        for i in raw_issues
    ]
    result = clarification.clarify_strategy(strategy_id, clarification.ClarifyRequest(resolutions=resolutions))

    assert len(result["applied"]) == 6
    assert result["failed"] == []
    assert result["status"] == "READY_FOR_BACKTEST"  # clarification resolved -- no more "unclear rule" errors

    # But actually running a backtest is still blocked -- manual_review
    # conditions are excluded from live execution until a human really
    # resolves them, same gate the Wizard's "bilkul naya" path uses.
    saved_cfg = lib.load(strategy_id)
    assert wizard.has_manual_review(saved_cfg)
    with pytest.raises(HTTPException) as exc_info:
        backtesting.run_backtest(backtesting.RunRequest(strategy_id=strategy_id, all_coins=False, symbols=["BTCUSDT"]))
    assert exc_info.value.status_code == 423
