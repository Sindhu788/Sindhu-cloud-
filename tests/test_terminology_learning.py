"""Item 4 (Parser & Extraction Improvements) -- Terminology Learning
(Persistent).

Proves the FULL loop, not just that a row gets written:
1. A user resolves an unrecognized indicator name via the Clarification
   Page's "replace_indicator" action -- this must persist the mapping to
   ai_dictionary_entries (dictionary_builder.save_learned_alias).
2. A SECOND, independent import containing the exact same unrecognized
   name must have it auto-resolved by self_correction.py's Level 1
   auto_repair -- deterministically, with zero AI calls -- instead of
   surfacing the same clarification question again.
"""

from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from backtest_engine import strategy_library as lib
from backtest_engine.validator import validate
from ai_integration import dictionary_builder, self_correction
from sindhu_web.api import clarification as clar_api


def _isolated_library(tmp_path, monkeypatch):
    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path / "library"))


def _strategy_with_unknown_indicator(name="smc_ob", **overrides):
    base = dict(
        name="Strategy Using an Unrecognized Indicator Name",
        raw_text="test",
        timeframes={"entry": "5m"},
        entry_conditions=[Condition(type="indicator_compare", indicator=name, op=">", value=1.0)],
        exit_conditions=[],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0),
        take_profit=SLTPSpec(type="rr", value=2.0),
        risk_pct=1.0, risk_reward=2.0,
    )
    base.update(overrides)
    return StrategyConfig(**base)


def test_unrecognized_indicator_is_a_real_clarification_issue_before_learning(test_db):
    cfg = _strategy_with_unknown_indicator()
    issues = clar_api.build_issues(cfg)
    invalid = [i for i in issues if i["kind"] == "invalid_indicator"]
    assert len(invalid) == 1
    assert invalid[0]["original_text"] == "smc_ob"


def test_resolving_via_replace_indicator_persists_the_alias(test_db, tmp_path, monkeypatch):
    _isolated_library(tmp_path, monkeypatch)
    strategy_id = lib.create(_strategy_with_unknown_indicator())
    cfg = lib.load(strategy_id)
    issue = [i for i in clar_api.build_issues(cfg) if i["kind"] == "invalid_indicator"][0]

    req = clar_api.ClarifyRequest(resolutions=[
        clar_api.ClarifyResolution(id=issue["id"], action="replace_indicator", value="order_block"),
    ])
    result = clar_api.clarify_strategy(strategy_id, req)
    assert len(result["applied"]) == 1

    entry = dictionary_builder.storage.get_ai_dictionary_entry("smc_ob")
    assert entry is not None
    assert entry["aliases"] == ["order_block"]


def test_the_same_unrecognized_term_is_auto_resolved_on_a_real_second_import(test_db, tmp_path, monkeypatch):
    """The actual proof: a genuinely separate second import (a fresh
    StrategyConfig, never touched by the first one) containing the exact
    same previously-unrecognized name must have it fixed automatically by
    self_correction's deterministic Level 1 repair -- no clarification
    question, no AI call."""
    _isolated_library(tmp_path, monkeypatch)

    # --- First import: unrecognized term, user clarifies it once. ---
    strategy_id = lib.create(_strategy_with_unknown_indicator())
    cfg1 = lib.load(strategy_id)
    issue = [i for i in clar_api.build_issues(cfg1) if i["kind"] == "invalid_indicator"][0]
    clar_api.clarify_strategy(strategy_id, clar_api.ClarifyRequest(resolutions=[
        clar_api.ClarifyResolution(id=issue["id"], action="replace_indicator", value="order_block"),
    ]))

    # --- Second, independent import with the SAME unrecognized term. ---
    cfg2 = _strategy_with_unknown_indicator(name="smc_ob", entry_conditions=[
        Condition(type="indicator_compare", indicator="smc_ob", op=">", value=1.0),
    ])
    assert cfg2.entry_conditions[0].indicator == "smc_ob"  # still unresolved going in

    repairs = self_correction.auto_repair(cfg2)
    assert any("smc_ob" in r and "order_block" in r for r in repairs)
    assert cfg2.entry_conditions[0].indicator == "order_block"

    # And critically: it no longer needs to ask the user about it at all.
    issues2 = clar_api.build_issues(cfg2)
    assert not any(i["kind"] == "invalid_indicator" for i in issues2)
    assert not any(e.startswith("Invalid indicator") for e in validate(cfg2))


def test_resolve_alias_returns_none_for_a_genuinely_unknown_term(test_db):
    assert dictionary_builder.resolve_alias("something_never_seen_before") is None
