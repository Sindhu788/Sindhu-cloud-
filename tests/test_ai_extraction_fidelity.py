"""Batch 2, Task 2 -- AI extraction (schema.py + strategy_builder.py) now
captures the rule types that PDH-PDL Signal Candle Strategy's original
extraction silently dropped: candle-range % filters, distance-based
discard filters, RR-based discard filters, signal-candle-anchored
stop-loss, the signal_candle_high/low entry mechanism, and partial
take-profit. Simulates a realistic AI JSON response end-to-end through
schema.parse_structured_response() -> strategy_builder.build_strategy_config().
"""

import json

from ai_integration import schema, strategy_builder


def _ai_response(**strategy_overrides):
    strategy = {
        "name": "Test Strategy",
        "timeframes": {"entry": "1m"},
        "indicators": [],
        "concepts_used": ["candle_break"],
        "entry_conditions": [
            {"type": "concept", "name": "candle_break", "direction": "bearish"},
            {"type": "candle_range_pct", "params": {"min_pct": 0.15, "max_pct": 3.0}},
        ],
        "exit_conditions": [],
        "confirmation_conditions": [],
        "stop_loss": {"type": "signal_candle", "value": 0.3},
        "take_profit": {"type": "rr", "value": 10.0},
        "risk_pct": 1.0,
        "risk_reward": 2.0,
        "session_filter": [],
        "day_filter": [],
        "entry_type": "signal_candle_low",
        "sl_distance_filter_pct": {"min_pct": 0.15, "max_pct": 1.5},
        "min_risk_reward_filter": 2.0,
        "primary_target_lookback_bars": 200,
        "partial_take_profit": {"trigger_rr": 2.0, "close_fraction": 0.8},
    }
    strategy.update(strategy_overrides)
    return json.dumps({"confidence": 90, "strategy": strategy, "lessons": [],
                        "dictionary_terms": [], "inferred_fields": [], "missing_rules": []})


def test_candle_range_pct_condition_survives_the_full_pipeline():
    parsed = schema.parse_structured_response(_ai_response())
    cfg = strategy_builder.build_strategy_config(parsed["strategy"], "Test Strategy", "raw text")
    range_conds = [c for c in cfg.entry_conditions if c.type == "candle_range_pct"]
    assert len(range_conds) == 1
    assert range_conds[0].params == {"min_pct": 0.15, "max_pct": 3.0}


def test_signal_candle_stop_loss_survives_the_full_pipeline():
    parsed = schema.parse_structured_response(_ai_response())
    cfg = strategy_builder.build_strategy_config(parsed["strategy"], "Test Strategy", "raw text")
    assert cfg.stop_loss.type == "signal_candle"
    assert cfg.stop_loss.value == 0.3


def test_signal_candle_stop_loss_without_a_buffer_value_is_kept_not_demoted():
    """Two-Focused-Day Push, Part 1/2: changed from the original
    conservative behavior (demoted to "unknown", losing the fact that the
    STOP STRUCTURE was already unambiguous) -- unlike fixed_pct/
    atr_multiple/rr, "anchored to the entry's own trigger candle" is a
    complete, real answer even with no buffer % given yet. Kept as
    signal_candle/value=None so Clarification Center can ask the exact,
    narrow question (just the buffer %) instead of falling back to a
    generic "pick any stop-loss mechanism" question that discards this
    structural information. See
    ai_integration.strategy_builder.build_stop_loss_take_profit and
    sindhu_web.api.clarification._find_unspecified_stop_loss_buffer_issue."""
    parsed = schema.parse_structured_response(_ai_response(stop_loss={"type": "signal_candle", "value": None}))
    cfg = strategy_builder.build_strategy_config(parsed["strategy"], "Test Strategy", "raw text")
    assert cfg.stop_loss.type == "signal_candle"
    assert cfg.stop_loss.value is None


def test_entry_type_signal_candle_low_survives_the_full_pipeline():
    parsed = schema.parse_structured_response(_ai_response())
    cfg = strategy_builder.build_strategy_config(parsed["strategy"], "Test Strategy", "raw text")
    assert cfg.entry_type == "signal_candle_low"


def test_unrecognized_entry_type_falls_back_to_market():
    parsed = schema.parse_structured_response(_ai_response(entry_type="teleport"))
    cfg = strategy_builder.build_strategy_config(parsed["strategy"], "Test Strategy", "raw text")
    assert cfg.entry_type == "market"


def test_discard_filters_survive_the_full_pipeline():
    parsed = schema.parse_structured_response(_ai_response())
    cfg = strategy_builder.build_strategy_config(parsed["strategy"], "Test Strategy", "raw text")
    assert cfg.sl_distance_filter_pct == {"min_pct": 0.15, "max_pct": 1.5}
    assert cfg.min_risk_reward_filter == 2.0
    assert cfg.primary_target_lookback_bars == 200


def test_partial_take_profit_survives_the_full_pipeline():
    parsed = schema.parse_structured_response(_ai_response())
    cfg = strategy_builder.build_strategy_config(parsed["strategy"], "Test Strategy", "raw text")
    assert cfg.partial_take_profit == {"trigger_rr": 2.0, "close_fraction": 0.8}


def test_incomplete_partial_take_profit_is_dropped_not_half_built():
    parsed = schema.parse_structured_response(
        _ai_response(partial_take_profit={"trigger_rr": 2.0})  # missing close_fraction
    )
    cfg = strategy_builder.build_strategy_config(parsed["strategy"], "Test Strategy", "raw text")
    assert cfg.partial_take_profit is None


def test_sl_distance_filter_with_neither_bound_is_dropped():
    parsed = schema.parse_structured_response(
        _ai_response(sl_distance_filter_pct={"min_pct": None, "max_pct": None})
    )
    cfg = strategy_builder.build_strategy_config(parsed["strategy"], "Test Strategy", "raw text")
    assert cfg.sl_distance_filter_pct is None


def test_candle_range_pct_with_no_bounds_is_demoted_to_raw():
    parsed = schema.parse_structured_response(_ai_response(
        entry_conditions=[{"type": "candle_range_pct", "params": {}}],
    ))
    cfg = strategy_builder.build_strategy_config(parsed["strategy"], "Test Strategy", "raw text")
    assert cfg.entry_conditions[0].type == "raw"


def test_a_strategy_saved_before_this_feature_is_completely_unaffected():
    """Every field this task adds defaults to None/"market" -- a response
    that never mentions any of them must produce byte-identical behavior
    to before this feature existed."""
    parsed = schema.parse_structured_response(_ai_response(
        entry_type=None, sl_distance_filter_pct=None, min_risk_reward_filter=None,
        primary_target_lookback_bars=None, partial_take_profit=None,
        stop_loss={"type": "fixed_pct", "value": 1.0},
        entry_conditions=[{"type": "concept", "name": "candle_break", "direction": "bearish"}],
    ))
    cfg = strategy_builder.build_strategy_config(parsed["strategy"], "Test Strategy", "raw text")
    assert cfg.entry_type == "market"
    assert cfg.sl_distance_filter_pct is None
    assert cfg.min_risk_reward_filter is None
    assert cfg.primary_target_lookback_bars is None
    assert cfg.partial_take_profit is None
