"""Batch 5, Task 1 -- the condensed sentence-level extraction prompt and
its parser. Real evidence during evidence-gathering: reusing the full
~6,200-token whole-document prompt on every tiny per-statement call
exhausted an entire day's provider token quota partway through ONE
27-statement document. This condensed prompt (~1,300 tokens) keeps the
essential vocabulary/schema while dropping the full prompt's extensive
worked-examples list, which matters far less when judging one
already-isolated statement rather than a whole document.
"""

from ai_integration import schema


def test_condensed_prompt_is_dramatically_smaller_than_the_full_prompt():
    full = schema.build_structured_extraction_prompt(content_type="strategy")
    condensed = schema.build_statement_extraction_prompt(content_type="strategy")
    assert len(condensed) < len(full) / 2


def test_condensed_prompt_still_carries_the_full_indicator_vocabulary():
    prompt = schema.build_statement_extraction_prompt()
    for indicator in ("pdh", "pdl", "candle_break", "liquidity_sweep", "fvg"):
        assert indicator in prompt


def test_condensed_prompt_still_carries_the_json_response_shape():
    prompt = schema.build_statement_extraction_prompt()
    assert '"is_rule"' in prompt
    assert '"entry_conditions"' in prompt
    assert '"stop_loss"' in prompt


def test_parse_statement_response_true_case():
    raw = '{"is_rule": true, "strategy": {"entry_conditions": [{"type": "concept", "name": "pdh", "direction": "bullish"}]}}'
    result = schema.parse_statement_response(raw)
    assert result["is_rule"] is True
    assert result["strategy"]["entry_conditions"][0]["name"] == "pdh"


def test_parse_statement_response_false_case_returns_no_strategy():
    raw = '{"is_rule": false, "strategy": {}}'
    result = schema.parse_statement_response(raw)
    assert result["is_rule"] is False
    assert result["strategy"] is None


def test_parse_statement_response_returns_none_for_unparseable_text():
    assert schema.parse_statement_response("not json") is None


def test_parse_statement_response_defaults_missing_is_rule_to_false():
    raw = '{"strategy": {}}'
    result = schema.parse_statement_response(raw)
    assert result["is_rule"] is False
