"""Item 3 (Parser & Extraction Improvements) -- Contradiction Detection.

Proves, with a deliberately contradictory document (a strategy config
requiring RSI < 30 AND RSI > 70 in the same AND-gated entry bucket -- can
never both be true on the same bar), that:

1. The contradiction is surfaced through the existing Clarification flow
   as a real, actionable issue (kind="contradiction") -- not silently
   dropped, and not silently resolved by picking one side.
2. The user can resolve it by choosing which of the two conflicting rules
   to keep; the other is removed and the contradiction clears.
3. The strategy-level ambiguity overview (Item 8) correctly counts it.
4. A second, structurally-unambiguous contradiction (bullish AND bearish
   concept conditions in one bucket) is still handled by the EXISTING
   self_correction.py auto-repair unchanged -- this task only adds
   coverage for the case that repair explicitly declines to guess at.
"""

from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from backtest_engine import strategy_library as lib
from backtest_engine.validator import validate
from sindhu_web.api import clarification as clar_api


def _isolated_library(tmp_path, monkeypatch):
    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path / "library"))


def _contradictory_rsi_strategy(**overrides):
    base = dict(
        name="Deliberately Contradictory RSI Strategy",
        raw_text="Enter when RSI is below 30 and RSI is above 70 at the same time.",
        timeframes={"entry": "5m"},
        entry_conditions=[
            Condition(type="indicator_compare", indicator="rsi", op="<", value=30.0, params={"period": 14}),
            Condition(type="indicator_compare", indicator="rsi", op=">", value=70.0, params={"period": 14}),
        ],
        exit_conditions=[],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0),
        take_profit=SLTPSpec(type="rr", value=2.0),
        risk_pct=1.0, risk_reward=2.0,
    )
    base.update(overrides)
    return StrategyConfig(**base)


def test_validator_confirms_the_document_is_genuinely_contradictory():
    cfg = _contradictory_rsi_strategy()
    errors = validate(cfg)
    assert any(e.startswith("Impossible combination") for e in errors)


def test_contradiction_is_surfaced_as_an_actionable_clarification_issue(test_db, tmp_path, monkeypatch):
    _isolated_library(tmp_path, monkeypatch)
    cfg = _contradictory_rsi_strategy()
    issues = clar_api.build_issues(cfg)
    contradiction_issues = [i for i in issues if i["kind"] == "contradiction"]
    assert len(contradiction_issues) == 1
    issue = contradiction_issues[0]
    # Never a dead end: a real strategy question the user must answer.
    assert len(issue["suggested_options"]) == 2
    assert all(o["action"] == "remove_condition" for o in issue["suggested_options"])
    # Never silently resolved -- validate() still reports it unresolved.
    assert any(e.startswith("Impossible combination") for e in validate(cfg))


def test_contradiction_is_never_silently_dropped_into_a_dead_end_other_issue():
    cfg = _contradictory_rsi_strategy()
    issues = clar_api.build_issues(cfg)
    # Before this fix, "Impossible combination" fell through to the generic
    # can_reject=False "other" bucket with no way to resolve it at all.
    assert not any(i["kind"] == "other" and "Impossible combination" in (i.get("reason") or "") for i in issues)


def test_user_can_resolve_the_contradiction_by_choosing_which_rule_to_keep(test_db, tmp_path, monkeypatch):
    _isolated_library(tmp_path, monkeypatch)
    strategy_id = lib.create(_contradictory_rsi_strategy())
    cfg = lib.load(strategy_id)
    assert any(e.startswith("Impossible combination") for e in validate(cfg))

    issue = [i for i in clar_api.build_issues(cfg) if i["kind"] == "contradiction"][0]
    keep_upper_option = next(o for o in issue["suggested_options"] if "remove \"rsi < 30.0\"" in o["label"])

    req = clar_api.ClarifyRequest(resolutions=[
        clar_api.ClarifyResolution(id=issue["id"], action="remove_condition", value=keep_upper_option["value"]),
    ])
    result = clar_api.clarify_strategy(strategy_id, req)
    assert len(result["applied"]) == 1

    resolved_cfg = lib.load(strategy_id)
    assert len(resolved_cfg.entry_conditions) == 1
    assert resolved_cfg.entry_conditions[0].op == ">"
    # The contradiction is genuinely gone now -- not hidden, actually fixed.
    assert not any(e.startswith("Impossible combination") for e in validate(resolved_cfg))


def test_ambiguity_overview_counts_an_unresolved_contradiction_as_uncertain_or_unresolved():
    cfg = _contradictory_rsi_strategy()
    issues = clar_api.build_issues(cfg)
    overview = clar_api.ambiguity_overview(90.0, issues)
    # A contradiction issue carries suggested_options (a specific, concrete
    # fix is available), so it counts as "uncertain" rather than a bare
    # "unresolved" dead end -- but it must show up somewhere, never vanish.
    assert overview["uncertain_count"] + overview["unresolved_count"] >= 1


def test_structurally_unambiguous_contradiction_is_still_auto_repaired_unchanged():
    """The OTHER kind of contradiction -- bullish AND bearish concept
    conditions in one bucket -- has an unambiguous structural fix
    (self_correction.py splits it into two entry paths). That existing,
    already-tested behavior must be untouched by this change."""
    from ai_integration import self_correction
    cfg = StrategyConfig(
        name="Mirrored Long/Short Flattened Into One Bucket",
        raw_text="test",
        timeframes={"entry": "5m"},
        entry_conditions=[
            Condition(type="concept", name="bos", direction="bullish"),
            Condition(type="concept", name="bos", direction="bearish"),
        ],
        exit_conditions=[Condition(type="concept", name="resistance", direction="bearish")],
        concepts_used=["bos", "resistance"],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0),
        take_profit=SLTPSpec(type="rr", value=2.0),
        risk_pct=1.0, risk_reward=2.0,
    )
    repairs = self_correction.auto_repair(cfg)
    assert repairs  # auto-repaired, not left as a dead end either
    assert not cfg.entry_conditions  # un-flattened into entry_rule_groups
    assert len(cfg.entry_rule_groups) == 2
