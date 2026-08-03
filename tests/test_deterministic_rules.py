"""Batch 5, Task 1 -- the deterministic (no-AI) rule counter. Pure code,
must be stable across runs on identical input (unlike the old AI-generated
inventory, which measurably varied 2/19 vs 9/19 on the same document)."""

from ai_integration import deterministic_rules as dr


def test_same_input_always_produces_the_same_count():
    text = "If price closes above PDH on the 1m chart, enter long. Stop loss is 0.3% below entry."
    r1 = dr.count_candidate_rules(text)
    r2 = dr.count_candidate_rules(text)
    assert r1 == r2


def test_finds_conditional_entry_and_stop_loss_lines():
    text = (
        "If price closes above PDH on the 1m chart, enter long.\n"
        "Stop loss is placed 0.3% below entry price.\n"
        "This strategy works well in trending markets.\n"  # not a rule -- descriptive commentary
    )
    result = dr.count_candidate_rules(text)
    texts = [c["text"] for c in result["candidates"]]
    assert any("PDH" in t for t in texts)
    assert any("Stop loss" in t for t in texts)


def test_markdown_headings_are_never_candidates():
    text = "### 1. Strategy Profile\n## Entry Rules\nIf price crosses above resistance, buy."
    result = dr.count_candidate_rules(text)
    for c in result["candidates"]:
        assert not c["text"].startswith("#")
    assert result["count"] == 1


def test_table_separator_rows_are_never_candidates():
    text = "| Field | Value |\n| --- | --- |\n| Entry | Buy above resistance level 1.5% |"
    result = dr.count_candidate_rules(text)
    assert all("---" not in c["text"] for c in result["candidates"])


def test_citation_markers_alone_do_not_create_false_positive_numeric_signal():
    text = "The timeframe used is daily [1, 2]."
    result = dr.count_candidate_rules(text)
    # "daily" alone (no percentage/pip/candle count) should not fire the
    # numeric_or_timeframe signal from a bare citation bracket.
    for c in result["candidates"]:
        assert "numeric_or_timeframe" not in c["signals"] or "%" in c["text"] or "pip" in c["text"].lower()


def test_pure_descriptive_text_with_no_rule_signal_is_not_a_candidate():
    text = "This document was written to summarize the overall trading philosophy."
    result = dr.count_candidate_rules(text)
    assert result["count"] == 0


def test_percentage_and_timeframe_terms_are_detected():
    text = "The signal candle's range must be between 0.15% and 3.0% on the 1-hour chart."
    result = dr.count_candidate_rules(text)
    assert result["count"] == 1
    assert "numeric_or_timeframe" in result["candidates"][0]["signals"]


def test_empty_text_returns_zero_candidates():
    assert dr.count_candidate_rules("") == {"count": 0, "candidates": []}
    assert dr.count_candidate_rules(None) == {"count": 0, "candidates": []}


def test_candidate_ids_are_sequential_starting_at_one():
    text = "If price crosses above resistance, buy.\nStop loss is 2% below entry.\nTake profit at 4%."
    result = dr.count_candidate_rules(text)
    ids = [c["id"] for c in result["candidates"]]
    assert ids == list(range(1, len(ids) + 1))


def test_long_paragraph_is_split_into_multiple_statements():
    text = ("Enter long when price closes above PDH on the 1-minute chart. "
            "Stop loss is placed 0.3% below the entry price. "
            "Take profit is set at a 2:1 risk-to-reward ratio.")
    result = dr.count_candidate_rules(text)
    assert result["count"] >= 3
