"""Strategy Wizard: a guided, form-based second import path into the exact
same StrategyConfig the free-text parser builds. Core rules under test:
NEVER GUESS (every stored value traces to an explicit wizard_data field)
and NEVER REJECT (an unmatched "Other" condition always saves, tagged for
manual review, rather than blocking the wizard or the whole strategy)."""

import pytest

from backtest_engine import wizard
from backtest_engine.validator import validate, known_indicator_names


# ------------------------------------------------------------- fully-dropdown build

def test_fully_dropdown_strategy_is_valid_and_backtestable():
    wizard_data = {
        "name": "Dropdown Only Strategy",
        "entry_timeframe": "5m",
        "bias_timeframe": "1h",
        "session": "london",
        "direction_mode": "long_only",
        "entry_conditions": [
            {"input_mode": "known", "concept": "fvg", "direction": "bullish", "role": "entry"},
            {"input_mode": "known", "concept": "bos", "direction": "bullish", "role": "entry"},
        ],
        "exit_conditions": [
            {"input_mode": "known", "concept": "choch", "direction": "bearish", "role": "exit"},
        ],
        "stop_loss": {"type": "fixed_pct", "value": 0.5},
        "take_profit": {"type": "rr", "value": 3.0},
        "risk_pct": 1.0,
    }
    config, trust = wizard.build_strategy_config(wizard_data)

    assert config.name == "Dropdown Only Strategy"
    assert config.timeframes == {"entry": "5m", "bias": "1h"}
    assert config.session_filter == ["london"]
    assert len(config.long_entry_conditions) == 2
    assert config.long_entry_conditions[0].name == "fvg"
    assert config.long_entry_conditions[0].direction == "bullish"
    assert config.stop_loss.type == "fixed_pct" and config.stop_loss.value == 0.5
    assert config.take_profit.type == "rr" and config.take_profit.value == 3.0
    assert config.risk_pct == 1.0

    assert trust["manual_review_count"] == 0
    assert trust["trust_score_pct"] == 100.0
    assert not wizard.has_manual_review(config)

    errors = validate(config)
    assert errors == [], errors


def test_indicator_with_period_registers_in_indicators_list():
    wizard_data = {
        "name": "EMA Strategy",
        "entry_timeframe": "15m",
        "direction_mode": "long_only",
        "entry_conditions": [
            {"input_mode": "known", "concept": "ema", "period": 50, "op": ">", "value": 0, "role": "entry"},
        ],
        "stop_loss": {"type": "atr_multiple", "value": 2.0},
        "take_profit": {"type": "fixed_pct", "value": 2.0},
        "risk_pct": 1.0,
    }
    config, trust = wizard.build_strategy_config(wizard_data)

    assert config.indicators == [{"name": "ema", "params": {"period": 50}, "role": "entry"}]
    cond = config.long_entry_conditions[0]
    assert cond.type == "indicator_compare" and cond.indicator == "ema" and cond.op == ">"
    assert trust["manual_review_count"] == 0


# ------------------------------------------------------------- Other / manual review

def test_unmatched_other_condition_saves_with_manual_review_tag():
    wizard_data = {
        "name": "Has Unknown Condition",
        "entry_timeframe": "5m",
        "direction_mode": "long_only",
        "entry_conditions": [
            {"input_mode": "known", "concept": "fvg", "direction": "bullish", "role": "entry"},
            {"input_mode": "other", "raw_text": "wait for the moon to align with Jupiter"},
        ],
        "stop_loss": {"type": "fixed_pct", "value": 0.5},
        "take_profit": {"type": "rr", "value": 2.0},
    }
    config, trust = wizard.build_strategy_config(wizard_data)

    assert len(config.long_entry_conditions) == 2
    unknown = config.long_entry_conditions[1]
    assert unknown.type == "raw"
    assert unknown.manual_review is True
    assert unknown.raw_source == "wait for the moon to align with Jupiter"

    assert trust["manual_review_count"] == 1
    assert trust["manual_review_items"][0]["raw_text"] == "wait for the moon to align with Jupiter"
    assert trust["trust_score_pct"] < 100.0
    assert wizard.has_manual_review(config)
    assert wizard.list_manual_review_conditions(config) == [unknown]


def test_other_condition_never_blocks_saving_the_strategy():
    """NEVER REJECT: the wizard must always be able to finish and save,
    even with a Manual Review item -- build_strategy_config never raises
    for this case."""
    wizard_data = {
        "name": "Still Saves",
        "direction_mode": "long_only",
        "entry_conditions": [{"input_mode": "other", "raw_text": "some undefined thing"}],
        "stop_loss": {}, "take_profit": {},
    }
    config, trust = wizard.build_strategy_config(wizard_data)
    assert config.name == "Still Saves"
    assert trust["manual_review_count"] == 1


def test_other_matched_to_known_concept_is_not_manual_review():
    """If the user (or the optional AI classify-other question) confirms
    the free text actually matches a known concept, it's treated as a
    normal structured condition, not manual review."""
    wizard_data = {
        "name": "Matched Other",
        "direction_mode": "long_only",
        "entry_conditions": [
            {"input_mode": "other", "raw_text": "gap in price nobody traded in", "matched_concept": "fvg", "direction": "bullish"},
        ],
        "stop_loss": {"type": "fixed_pct", "value": 1.0},
        "take_profit": {"type": "rr", "value": 2.0},
    }
    config, trust = wizard.build_strategy_config(wizard_data)
    cond = config.long_entry_conditions[0]
    assert cond.type == "concept" and cond.name == "fvg" and not cond.manual_review
    assert trust["manual_review_count"] == 0


def test_unsupported_sl_type_becomes_manual_review_not_silent_noop():
    """The engine has no "fixed_points" SLTPSpec type -- selecting it must
    never silently produce a non-functional stop_loss; it's flagged for
    manual review instead."""
    wizard_data = {
        "name": "Points SL",
        "direction_mode": "long_only",
        "entry_conditions": [{"input_mode": "known", "concept": "fvg", "direction": "bullish"}],
        "stop_loss": {"type": "fixed_points", "value": 50, "raw_source": "50 points below entry"},
        "take_profit": {"type": "rr", "value": 2.0},
    }
    config, trust = wizard.build_strategy_config(wizard_data)
    assert config.stop_loss.type == "unknown"
    assert any(i["section"] == "Stop Loss" for i in trust["manual_review_items"])


# ------------------------------------------------------------- mirror direction

def test_mirror_direction_generates_correct_opposite_rules():
    wizard_data = {
        "name": "Mirror Strategy",
        "direction_mode": "both_mirror",
        "entry_conditions": [
            {"input_mode": "known", "concept": "fvg", "direction": "bullish", "role": "entry"},
            {"input_mode": "known", "concept": "choch", "direction": "bullish", "role": "entry"},
        ],
        "stop_loss": {"type": "structure"},
        "take_profit": {"type": "rr", "value": 4.0},
    }
    config, trust = wizard.build_strategy_config(wizard_data)

    assert [c.direction for c in config.long_entry_conditions] == ["bullish", "bullish"]
    assert [c.direction for c in config.short_entry_conditions] == ["bearish", "bearish"]
    assert [c.name for c in config.long_entry_conditions] == [c.name for c in config.short_entry_conditions]

    errors = validate(config)
    assert not any("keep one direction per strategy" in e for e in errors)


def test_mirror_direction_preserves_manual_review_text_unchanged_both_sides():
    wizard_data = {
        "name": "Mirror With Unknown",
        "direction_mode": "both_mirror",
        "entry_conditions": [
            {"input_mode": "other", "raw_text": "something undefined and direction-specific"},
        ],
        "stop_loss": {"type": "fixed_pct", "value": 1.0},
        "take_profit": {"type": "rr", "value": 2.0},
    }
    config, trust = wizard.build_strategy_config(wizard_data)
    assert config.long_entry_conditions[0].raw_source == config.short_entry_conditions[0].raw_source
    assert config.long_entry_conditions[0].manual_review and config.short_entry_conditions[0].manual_review


def test_both_independent_does_not_mirror():
    wizard_data = {
        "name": "Independent Strategy",
        "direction_mode": "both_independent",
        "long_entry_conditions": [{"input_mode": "known", "concept": "fvg", "direction": "bullish"}],
        "short_entry_conditions": [
            {"input_mode": "known", "concept": "fvg", "direction": "bearish"},
            {"input_mode": "known", "concept": "liquidity_sweep", "direction": "bearish"},
        ],
        "stop_loss": {"type": "structure"},
        "take_profit": {"type": "rr", "value": 3.0},
    }
    config, trust = wizard.build_strategy_config(wizard_data)
    assert len(config.long_entry_conditions) == 1
    assert len(config.short_entry_conditions) == 2  # NOT mirrored from long (which only has 1)


# ------------------------------------------------------------- concept catalog is real, not hardcoded

def test_known_concept_catalog_matches_validator_source_of_truth():
    catalog = wizard.known_concept_catalog()
    all_from_catalog = set(catalog["concepts"]) | set(catalog["indicators"])
    assert all_from_catalog == set(known_indicator_names())
    assert "fvg" in catalog["concepts"]
    assert "ema" in catalog["indicators"]


# ------------------------------------------------------------- filters (Step 7)

def test_filters_are_appended_to_the_active_entry_bucket():
    wizard_data = {
        "name": "Filtered Strategy",
        "direction_mode": "long_only",
        "entry_conditions": [{"input_mode": "known", "concept": "fvg", "direction": "bullish"}],
        "filters": [{"input_mode": "known", "concept": "session_open", "role": "entry"}],
        "stop_loss": {"type": "fixed_pct", "value": 1.0},
        "take_profit": {"type": "rr", "value": 2.0},
    }
    config, trust = wizard.build_strategy_config(wizard_data)
    assert len(config.long_entry_conditions) == 2
    assert config.long_entry_conditions[1].name == "session_open"


def test_trust_score_counts_user_inputs_not_expanded_duplicated_conditions():
    """A mirror-direction condition and a filter (appended to BOTH long and
    short entry buckets) are the SAME user input represented twice inside
    the final StrategyConfig -- the trust score must count them once, not
    double the denominator without doubling the manual-review numerator to
    match (which would silently inflate the score)."""
    wizard_data = {
        "name": "Trust Score Doubling Check",
        "direction_mode": "both_mirror",
        "entry_conditions": [
            {"input_mode": "known", "concept": "fvg", "direction": "bullish"},
            {"input_mode": "known", "concept": "choch", "direction": "bullish"},
            {"input_mode": "known", "concept": "fvg", "direction": "bullish"},
            {"input_mode": "other", "raw_text": "significant sign of strength or displacement"},
            {"input_mode": "other", "raw_text": "clean response or immediate rejection off the midpoint"},
        ],
        "exit_conditions": [
            {"input_mode": "other", "raw_text": "move stop to breakeven"},
            {"input_mode": "other", "raw_text": "full exit, take the entire trade off the table"},
        ],
        "filters": [
            {"input_mode": "other", "raw_text": "avoid chop"},
            {"input_mode": "other", "raw_text": "trendline confluence"},
            {"input_mode": "other", "raw_text": "force filter"},
            {"input_mode": "other", "raw_text": "level invalidation"},
        ],
        "stop_loss": {"type": "signal_candle"},
        "take_profit": {"type": "rr", "value": 4.0},
    }
    config, trust = wizard.build_strategy_config(wizard_data)

    # 5 entry + 2 exit + 4 filters + SL + TP = 13 distinct user inputs;
    # 2 entry + 2 exit + 4 filters = 8 need manual review.
    assert trust["total_conditions"] == 13
    assert trust["manual_review_count"] == 8
    assert trust["trust_score_pct"] == pytest.approx(38.5, abs=0.1)

    # The expanded config nonetheless has the filters/mirrored conditions
    # present TWICE (once per direction) -- that's correct for execution,
    # just not for the trust-score denominator.
    assert len(config.long_entry_conditions) == 9
    assert len(config.short_entry_conditions) == 9


def test_invalid_direction_mode_raises_clearly():
    with pytest.raises(ValueError):
        wizard.build_strategy_config({"name": "Bad", "direction_mode": "sideways"})
