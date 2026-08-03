"""Batch 5, Task 1 -- sentence-level extraction with retry-until-
reconciled. Mocked AI calls (no network) -- covers the orchestration:
one call per deterministic candidate, additive merge, and retry of
whatever's still unresolved after the first pass, up to the retry limit,
never fabricating a rule to force reconciliation.
"""

from unittest.mock import patch

from ai_integration import sentence_level_extraction as sle
from ai_integration import schema


def _strategy_fragment(**overrides):
    base = {
        "name": "", "timeframes": {}, "indicators": [], "concepts_used": [],
        "entry_conditions": [], "long_entry_conditions": [], "short_entry_conditions": [],
        "entry_rule_groups": [], "exit_conditions": [], "confirmation_conditions": [],
        "stop_loss": {"type": "unknown", "value": None, "level": None},
        "take_profit": {"type": "unknown", "value": None, "level": None},
        "risk_pct": None, "risk_reward": None, "session_filter": [], "trend_filter": None,
        "day_filter": [], "breakeven_at_rr": None, "entry_type": "market",
        "entry_price_offset_pct": None, "sl_distance_filter_pct": None,
        "min_risk_reward_filter": None, "primary_target_lookback_bars": None,
        "partial_take_profit": None,
    }
    base.update(overrides)
    return base


def test_one_call_per_deterministic_candidate():
    text = "If price closes above PDH, buy.\nStop loss is 0.3% below entry."

    def fake_call(statement_text, chain, prompt, endpoint, parse_fn):
        return {"is_rule": True, "strategy": _strategy_fragment(
            entry_conditions=[{"type": "raw", "text": statement_text}])}, "groq", None

    with patch.object(sle, "call_provider_chain_generic", side_effect=fake_call), \
         patch("ai_integration.config.provider_fallback_chain", return_value=["groq"]):
        result = sle.run_sentence_level_extraction(text)

    assert result["call_count"] == result["rule_inventory"]["count"]
    assert result["comparison"]["captured_count"] == result["rule_inventory"]["count"]


def test_deterministic_count_never_varies_between_runs():
    text = "If price closes above PDH, buy.\nStop loss is 0.3% below entry.\nTake profit at 2% above entry."

    def fake_call(statement_text, chain, prompt, endpoint, parse_fn):
        return {"is_rule": True, "strategy": _strategy_fragment()}, "groq", None

    with patch.object(sle, "call_provider_chain_generic", side_effect=fake_call), \
         patch("ai_integration.config.provider_fallback_chain", return_value=["groq"]):
        r1 = sle.run_sentence_level_extraction(text)
        r2 = sle.run_sentence_level_extraction(text)

    assert r1["rule_inventory"]["count"] == r2["rule_inventory"]["count"]


def test_ai_disagreeing_a_candidate_is_a_rule_is_resolved_not_missing():
    text = "If price closes above PDH, buy.\nMany traders place their stop loss above recent highs, generally speaking."

    def fake_call(statement_text, chain, prompt, endpoint, parse_fn):
        if "generally speaking" in statement_text:
            return {"is_rule": False, "strategy": None}, "groq", None
        return {"is_rule": True, "strategy": _strategy_fragment(
            entry_conditions=[{"type": "raw", "text": statement_text}])}, "groq", None

    with patch.object(sle, "call_provider_chain_generic", side_effect=fake_call), \
         patch("ai_integration.config.provider_fallback_chain", return_value=["groq"]):
        result = sle.run_sentence_level_extraction(text)

    statuses = {r["status"] for r in result["comparison"]["rules"]}
    assert "not_a_rule" in statuses
    assert result["retry_count"] == 0  # a "not a rule" verdict is resolved, never retried


def test_failed_call_is_retried_with_exact_original_text():
    text = "If price closes above PDH, buy."
    calls = []

    def fake_call(statement_text, chain, prompt, endpoint, parse_fn):
        calls.append(statement_text)
        if len(calls) == 1:
            return None, None, "provider error"
        return {"is_rule": True, "strategy": _strategy_fragment(
            entry_conditions=[{"type": "raw", "text": statement_text}])}, "groq", None

    with patch.object(sle, "call_provider_chain_generic", side_effect=fake_call), \
         patch("ai_integration.config.provider_fallback_chain", return_value=["groq"]):
        result = sle.run_sentence_level_extraction(text)

    assert result["retry_count"] == 1
    assert len(calls) == 2
    assert calls[0] == calls[1]  # exact same original text on retry
    assert result["comparison"]["captured_count"] == 1


def test_stops_retrying_after_max_retries_and_never_fabricates():
    text = "If price closes above PDH, buy."

    def always_fails(statement_text, chain, prompt, endpoint, parse_fn):
        return None, None, "provider error"

    with patch.object(sle, "call_provider_chain_generic", side_effect=always_fails), \
         patch("ai_integration.config.provider_fallback_chain", return_value=["groq"]):
        result = sle.run_sentence_level_extraction(text, max_retries=2)

    assert result["retry_count"] == 2
    assert result["comparison"]["captured_count"] == 0
    assert result["comparison"]["rules"][0]["status"] == "missing"
    assert result["comparison"]["rules"][0]["text"] == "If price closes above PDH, buy."
    assert result["result"] is None  # nothing fabricated


def test_merge_is_additive_across_many_small_fragments():
    text = "If price closes above PDH, buy.\nStop loss is 0.3% below entry.\nTake profit at 2% above entry."

    def fake_call(statement_text, chain, prompt, endpoint, parse_fn):
        if "PDH" in statement_text:
            frag = _strategy_fragment(entry_conditions=[{"type": "raw", "text": "pdh entry"}])
        elif "Stop loss" in statement_text:
            frag = _strategy_fragment(stop_loss={"type": "fixed_pct", "value": 0.3, "level": None})
        else:
            frag = _strategy_fragment(take_profit={"type": "fixed_pct", "value": 2.0, "level": None})
        return {"is_rule": True, "strategy": frag}, "groq", None

    with patch.object(sle, "call_provider_chain_generic", side_effect=fake_call), \
         patch("ai_integration.config.provider_fallback_chain", return_value=["groq"]):
        result = sle.run_sentence_level_extraction(text)

    strategy = result["result"]["strategy"]
    assert len(strategy["entry_conditions"]) == 1
    assert strategy["stop_loss"]["type"] == "fixed_pct"
    assert strategy["take_profit"]["type"] == "fixed_pct"


def test_no_candidates_at_all_returns_empty_result_without_calling_ai():
    text = "This document has no rule-shaped content at all."
    with patch.object(sle, "call_provider_chain_generic") as mock_call:
        result = sle.run_sentence_level_extraction(text)
    mock_call.assert_not_called()
    assert result["result"] is None
    assert result["comparison"]["expected_count"] == 0


def test_no_provider_chain_returns_empty_result():
    text = "If price closes above PDH, buy."
    with patch("ai_integration.config.provider_fallback_chain", return_value=[]):
        result = sle.run_sentence_level_extraction(text)
    assert result["result"] is None
    assert result["call_count"] == 0
