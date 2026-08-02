"""Batch 3, Task 1 -- multi-pass AI extraction with rule counting.
Covers: the rule-inventory parser, the comparison-response parser, the
scope-disjoint merge of the three focused passes, the full orchestration
(mocked AI calls -- no network), and the extraction_fidelity_reports
storage layer Task 1/2/3 all read from.
"""

from unittest.mock import patch

from ai_integration import multi_pass_extraction as mpe
from ai_integration import schema
from data_engine import storage


# ------------------------------------------------------------ schema parsers

def test_parse_rule_inventory_response_returns_numbered_rules():
    raw = '{"rules": [{"text": "price above PDH", "category": "entry"}, {"text": "SL at 0.3% buffer", "category": "exit"}]}'
    result = schema.parse_rule_inventory_response(raw)
    assert result["count"] == 2
    assert result["rules"][0] == {"id": 1, "text": "price above PDH", "category": "entry"}
    assert result["rules"][1]["category"] == "exit"


def test_parse_rule_inventory_response_defaults_unknown_category_to_entry_not_dropped():
    raw = '{"rules": [{"text": "some rule", "category": "banana"}]}'
    result = schema.parse_rule_inventory_response(raw)
    assert result["count"] == 1
    assert result["rules"][0]["category"] == "entry"


def test_parse_rule_inventory_response_skips_blank_text():
    raw = '{"rules": [{"text": "", "category": "entry"}, {"text": "real rule", "category": "entry"}]}'
    result = schema.parse_rule_inventory_response(raw)
    assert result["count"] == 1


def test_parse_rule_inventory_response_returns_none_for_unparseable_text():
    assert schema.parse_rule_inventory_response("not json at all") is None


def test_parse_comparison_response_reads_status_and_captured_as():
    raw = '{"results": [{"rule_id": 1, "status": "captured", "captured_as": "price_compare pdh"}, {"rule_id": 2, "status": "missing", "captured_as": null}]}'
    result = schema.parse_comparison_response(raw)
    assert result["results"][0] == {"rule_id": 1, "status": "captured", "captured_as": "price_compare pdh"}
    assert result["results"][1]["status"] == "missing"


def test_parse_comparison_response_defaults_bad_status_to_missing_not_captured():
    """Never let a malformed status silently read as success."""
    raw = '{"results": [{"rule_id": 1, "status": "sort-of", "captured_as": "x"}]}'
    result = schema.parse_comparison_response(raw)
    assert result["results"][0]["status"] == "missing"


# ------------------------------------------------------------ scoped prompt builder

def test_scoped_prompt_rejects_unknown_scope():
    import pytest
    with pytest.raises(ValueError):
        schema.build_scoped_extraction_prompt("bogus")


def test_each_scope_produces_a_distinct_prompt():
    entry = schema.build_scoped_extraction_prompt("entry")
    exit_ = schema.build_scoped_extraction_prompt("exit")
    filters = schema.build_scoped_extraction_prompt("filters")
    assert "ENTRY RULES ONLY" in entry
    assert "STOP-LOSS, AND TAKE-PROFIT ONLY" in exit_
    assert "RISK/POSITION-SIZING RULES ONLY" in filters


# ------------------------------------------------------------ scope-disjoint merge

def test_merge_scoped_strategies_combines_disjoint_fields():
    entry_s = {"name": "Test", "entry_conditions": [{"type": "concept", "name": "pdh"}], "entry_type": "market"}
    exit_s = {"stop_loss": {"type": "fixed_pct", "value": 1.0, "level": None},
              "take_profit": {"type": "rr", "value": 2.0, "level": None}}
    filters_s = {"risk_pct": 1.0, "min_risk_reward_filter": 2.0, "primary_target_lookback_bars": 200}

    merged = mpe._merge_scoped_strategies(entry_s, exit_s, filters_s)
    assert merged["name"] == "Test"
    assert merged["entry_conditions"] == entry_s["entry_conditions"]
    assert merged["stop_loss"] == exit_s["stop_loss"]
    assert merged["take_profit"] == exit_s["take_profit"]
    assert merged["risk_pct"] == 1.0
    assert merged["min_risk_reward_filter"] == 2.0
    assert merged["primary_target_lookback_bars"] == 200


def test_merge_scoped_strategies_unions_candle_range_filter_from_filters_pass_into_entry_conditions():
    entry_s = {"entry_conditions": [{"type": "concept", "name": "candle_break"}]}
    filters_s = {"entry_conditions": [{"type": "candle_range_pct", "params": {"min_pct": 0.15, "max_pct": 3.0}}]}
    merged = mpe._merge_scoped_strategies(entry_s, None, filters_s)
    assert len(merged["entry_conditions"]) == 2


def test_merge_scoped_strategies_returns_none_when_all_three_passes_are_empty():
    assert mpe._merge_scoped_strategies(None, None, None) is None
    assert mpe._merge_scoped_strategies({}, {}, {}) is None


# ------------------------------------------------------------ full orchestration (mocked AI)

def _fake_extraction(strategy_dict, confidence=90):
    base = dict(schema._REQUIRED_KEYS)
    base["confidence"] = confidence
    base["strategy"] = strategy_dict
    return base


def test_run_multi_pass_extraction_makes_exactly_five_calls_and_merges_correctly():
    inventory_response = {"rules": [
        {"id": 1, "text": "enter when price above PDH", "category": "entry"},
        {"id": 2, "text": "SL = signal high * 1.003", "category": "exit"},
        {"id": 3, "text": "risk 1% per trade", "category": "filters"},
    ], "count": 3}
    entry_response = _fake_extraction({"entry_conditions": [{"type": "concept", "name": "pdh"}]})
    exit_response = _fake_extraction({"stop_loss": {"type": "signal_candle", "value": 0.3, "level": None}})
    filters_response = _fake_extraction({"risk_pct": 1.0})
    comparison_response = {"results": [
        {"rule_id": 1, "status": "captured", "captured_as": "pdh condition"},
        {"rule_id": 2, "status": "captured", "captured_as": "signal_candle stop"},
        {"rule_id": 3, "status": "missing", "captured_as": None},
    ]}

    call_log = []

    def fake_call(text, chain, prompt, endpoint_label, parse_fn):
        call_log.append(endpoint_label)
        if endpoint_label == "/ai/import/rule-inventory":
            return inventory_response, "groq", None
        if endpoint_label == "/ai/import/scoped-extraction-entry":
            return entry_response, "groq", None
        if endpoint_label == "/ai/import/scoped-extraction-exit":
            return exit_response, "groq", None
        if endpoint_label == "/ai/import/scoped-extraction-filters":
            return filters_response, "groq", None
        if endpoint_label == "/ai/import/extraction-comparison":
            return comparison_response, "groq", None
        raise AssertionError(f"unexpected endpoint {endpoint_label}")

    with patch.object(mpe, "call_provider_chain_generic", side_effect=fake_call), \
         patch("ai_integration.config.provider_fallback_chain", return_value=["groq"]):
        result = mpe.run_multi_pass_extraction("some raw text", content_type="strategy")

    assert result["call_count"] == 5
    assert call_log == [
        "/ai/import/rule-inventory",
        "/ai/import/scoped-extraction-entry",
        "/ai/import/scoped-extraction-exit",
        "/ai/import/scoped-extraction-filters",
        "/ai/import/extraction-comparison",
    ]
    assert result["rule_inventory"]["count"] == 3
    assert result["comparison"]["expected_count"] == 3
    assert result["comparison"]["captured_count"] == 2
    statuses = {r["id"]: r["status"] for r in result["comparison"]["rules"]}
    assert statuses == {1: "captured", 2: "captured", 3: "missing"}
    assert result["result"]["strategy"]["risk_pct"] == 1.0
    assert result["result"]["strategy"]["stop_loss"]["type"] == "signal_candle"


def test_run_multi_pass_extraction_marks_rules_unknown_not_captured_when_comparison_call_fails():
    inventory_response = {"rules": [{"id": 1, "text": "rule one", "category": "entry"}], "count": 1}

    def fake_call(text, chain, prompt, endpoint_label, parse_fn):
        if endpoint_label == "/ai/import/rule-inventory":
            return inventory_response, "groq", None
        if endpoint_label == "/ai/import/extraction-comparison":
            return None, None, "all providers failed"
        return _fake_extraction({}), "groq", None

    with patch.object(mpe, "call_provider_chain_generic", side_effect=fake_call), \
         patch("ai_integration.config.provider_fallback_chain", return_value=["groq"]):
        result = mpe.run_multi_pass_extraction("some raw text")

    assert result["comparison"]["rules"][0]["status"] == "unknown"
    assert result["comparison"]["captured_count"] == 0


def test_run_multi_pass_extraction_no_provider_chain_returns_empty_without_calling_anything():
    with patch("ai_integration.config.provider_fallback_chain", return_value=[]):
        result = mpe.run_multi_pass_extraction("text")
    assert result["call_count"] == 0
    assert result["result"] is None


# ------------------------------------------------------------ Task 2: auto-retry

def _base_extraction_mocks(inventory_rules, entry=None, exit_=None, filters=None, comparison=None):
    entry = entry or _fake_extraction({})
    exit_ = exit_ or _fake_extraction({})
    filters = filters or _fake_extraction({})
    comparison = comparison if comparison is not None else {"results": []}

    def fake_call(text, chain, prompt, endpoint_label, parse_fn):
        if endpoint_label == "/ai/import/rule-inventory":
            return {"rules": inventory_rules, "count": len(inventory_rules)}, "groq", None
        if endpoint_label == "/ai/import/scoped-extraction-entry":
            return entry, "groq", None
        if endpoint_label == "/ai/import/scoped-extraction-exit":
            return exit_, "groq", None
        if endpoint_label == "/ai/import/scoped-extraction-filters":
            return filters, "groq", None
        if endpoint_label == "/ai/import/extraction-comparison":
            return comparison, "groq", None
        raise AssertionError(f"unexpected first-pass endpoint {endpoint_label}")

    return fake_call


def test_retry_does_not_trigger_when_nothing_is_missing():
    inventory_rules = [{"id": 1, "text": "rule one", "category": "entry"}]
    first_comparison = {"results": [{"rule_id": 1, "status": "captured", "captured_as": "x"}]}
    fake_call = _base_extraction_mocks(inventory_rules, comparison=first_comparison)

    with patch.object(mpe, "call_provider_chain_generic", side_effect=fake_call), \
         patch("ai_integration.config.provider_fallback_chain", return_value=["groq"]):
        result = mpe.run_multi_pass_extraction_with_retry("text")

    assert result["retry_count"] == 0
    assert result["call_count"] == 5  # exactly the first-pass count, no retry calls
    assert result["comparison"]["captured_count"] == 1


def test_retry_recovers_a_deliberately_dropped_rule():
    """The core Task 2 scenario: first pass misses rule 2 entirely, the
    retry call supplies it, and the re-run comparison marks it captured."""
    inventory_rules = [
        {"id": 1, "text": "enter on BOS", "category": "entry"},
        {"id": 2, "text": "SL at signal candle low", "category": "exit"},
    ]
    first_comparison = {"results": [
        {"rule_id": 1, "status": "captured", "captured_as": "bos condition"},
        {"rule_id": 2, "status": "missing", "captured_as": None},
    ]}
    retry_fragment = _fake_extraction({"stop_loss": {"type": "signal_candle", "value": 0.3, "level": None}})
    retry_comparison = {"results": [
        {"rule_id": 1, "status": "captured", "captured_as": "bos condition"},
        {"rule_id": 2, "status": "captured", "captured_as": "signal_candle stop recovered on retry"},
    ]}

    first_pass_call = _base_extraction_mocks(
        inventory_rules,
        entry=_fake_extraction({"entry_conditions": [{"type": "concept", "name": "bos", "direction": "bullish"}]}),
        comparison=first_comparison,
    )
    retry_calls = []

    def fake_call(text, chain, prompt, endpoint_label, parse_fn):
        if endpoint_label == "/ai/import/retry-1":
            retry_calls.append(prompt)
            return retry_fragment, "groq", None
        if endpoint_label == "/ai/import/extraction-comparison-retry-1":
            return retry_comparison, "groq", None
        return first_pass_call(text, chain, prompt, endpoint_label, parse_fn)

    with patch.object(mpe, "call_provider_chain_generic", side_effect=fake_call), \
         patch("ai_integration.config.provider_fallback_chain", return_value=["groq"]):
        result = mpe.run_multi_pass_extraction_with_retry("text")

    assert result["retry_count"] == 1
    assert result["call_count"] == 7  # 5 first-pass + retry extraction + retry comparison
    assert result["comparison"]["captured_count"] == 2
    assert result["result"]["strategy"]["stop_loss"]["type"] == "signal_candle"
    # the retry prompt named the specific missing rule by its exact text
    assert "SL at signal candle low" in retry_calls[0]
    assert "enter on BOS" not in retry_calls[0]  # already-captured rule not re-requested


def test_retry_stops_after_three_attempts_when_still_missing():
    inventory_rules = [{"id": 1, "text": "an unrecoverable rule", "category": "entry"}]
    still_missing = {"results": [{"rule_id": 1, "status": "missing", "captured_as": None}]}
    first_call = _base_extraction_mocks(inventory_rules, comparison=still_missing)
    retry_attempts = {"extraction": 0, "comparison": 0}

    def fake_call(text, chain, prompt, endpoint_label, parse_fn):
        if endpoint_label.startswith("/ai/import/retry-"):
            retry_attempts["extraction"] += 1
            return _fake_extraction({}), "groq", None
        if endpoint_label.startswith("/ai/import/extraction-comparison-retry-"):
            retry_attempts["comparison"] += 1
            return still_missing, "groq", None
        return first_call(text, chain, prompt, endpoint_label, parse_fn)

    with patch.object(mpe, "call_provider_chain_generic", side_effect=fake_call), \
         patch("ai_integration.config.provider_fallback_chain", return_value=["groq"]):
        result = mpe.run_multi_pass_extraction_with_retry("text")

    assert result["retry_count"] == 3
    assert retry_attempts["extraction"] == 3
    assert retry_attempts["comparison"] == 3
    assert result["comparison"]["rules"][0]["status"] == "missing"


def test_unresolved_rule_after_retries_keeps_its_original_text_never_fabricated():
    inventory_rules = [{"id": 1, "text": "a genuinely unrecoverable rule, verbatim", "category": "filters"}]
    still_missing = {"results": [{"rule_id": 1, "status": "missing", "captured_as": None}]}
    fake_call = _base_extraction_mocks(inventory_rules, comparison=still_missing)

    def wrapped(text, chain, prompt, endpoint_label, parse_fn):
        if endpoint_label.startswith("/ai/import/retry-") or endpoint_label.startswith("/ai/import/extraction-comparison-retry-"):
            if "comparison" in endpoint_label:
                return still_missing, "groq", None
            return _fake_extraction({}), "groq", None
        return fake_call(text, chain, prompt, endpoint_label, parse_fn)

    with patch.object(mpe, "call_provider_chain_generic", side_effect=wrapped), \
         patch("ai_integration.config.provider_fallback_chain", return_value=["groq"]):
        result = mpe.run_multi_pass_extraction_with_retry("text")

    unresolved = result["comparison"]["rules"][0]
    assert unresolved["status"] == "missing"
    assert unresolved["text"] == "a genuinely unrecoverable rule, verbatim"
    assert unresolved["captured_as"] is None


def test_retry_merge_never_overwrites_an_already_captured_field():
    existing = {"stop_loss": {"type": "fixed_pct", "value": 1.0, "level": None}, "entry_conditions": [{"type": "concept", "name": "bos"}]}
    fragment = {"stop_loss": {"type": "signal_candle", "value": 0.5, "level": None}, "entry_conditions": [{"type": "concept", "name": "fvg"}]}
    merged = mpe._merge_retry_fragment(existing, fragment)
    assert merged["stop_loss"]["type"] == "fixed_pct"  # not overwritten by the retry's guess
    assert len(merged["entry_conditions"]) == 2  # new condition added, old one kept


# ------------------------------------------------------------ storage

def test_save_and_get_extraction_fidelity_report(test_db):
    rules = [{"id": 1, "text": "rule 1", "category": "entry", "status": "captured", "captured_as": "x"}]
    storage.save_extraction_fidelity_report("hash1", 3, 2, 5, rules, "groq", "2026-01-01T00:00:00+00:00")
    report = storage.get_extraction_fidelity_report("hash1")
    assert report["expected_rule_count"] == 3
    assert report["captured_rule_count"] == 2
    assert report["call_count"] == 5
    assert report["rules"] == rules
    assert report["strategy_id"] is None


def test_extraction_fidelity_report_upserts_on_same_content_hash(test_db):
    storage.save_extraction_fidelity_report("hash1", 3, 1, 5, [], "groq", "2026-01-01T00:00:00+00:00")
    storage.save_extraction_fidelity_report("hash1", 3, 3, 8, [], "groq", "2026-01-01T01:00:00+00:00", retry_count=1)
    report = storage.get_extraction_fidelity_report("hash1")
    assert report["captured_rule_count"] == 3
    assert report["retry_count"] == 1


def test_set_extraction_fidelity_strategy_id_links_report_to_strategy(test_db):
    storage.save_extraction_fidelity_report("hash1", 3, 2, 5, [], "groq", "2026-01-01T00:00:00+00:00")
    storage.set_extraction_fidelity_strategy_id("hash1", "strat123")
    report = storage.get_extraction_fidelity_report("hash1")
    assert report["strategy_id"] == "strat123"
    by_strategy = storage.get_extraction_fidelity_report_for_strategy("strat123")
    assert by_strategy["content_hash"] == "hash1"
