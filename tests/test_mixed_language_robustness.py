"""Item 9 (Parser & Extraction Improvements) -- Mixed-Language & Slang
Robustness.

Tests deterministic parsing (backtest_engine.strategy_parser) against a
genuinely mixed English / Roman Urdu / trading-slang document. Roman Urdu
already had PARTIAL support here (upar/neeche recognized as above/below,
"aur" as "and") -- but only in English word order (comparison word THEN
number). Urdu is SOV word order, so a threshold is very commonly written
NUMBER-then-comparison-word instead ("RSI 30 se neeche" = "RSI below 30"),
which fell all the way through to a bare bullish/bearish concept match and
lost the actual numeric rule. This file proves the fix, and is honest
about what still degrades rather than claiming full coverage.
"""

from backtest_engine.strategy_parser import parse_conditions


def test_reversed_word_order_rsi_threshold_is_understood():
    """The concrete bug: 'RSI 30 se neeche' (number-before-operator, the
    natural Roman Urdu order) previously lost the actual threshold and
    fell back to a vague concept match on 'buy'."""
    conds = parse_conditions("RSI 30 se neeche jaye to buy karo")
    compares = [c for c in conds if c.type == "indicator_compare"]
    assert len(compares) == 1
    assert compares[0].indicator == "rsi"
    assert compares[0].op == "<"
    assert compares[0].value == 30.0


def test_reversed_word_order_upar_above_is_understood():
    conds = parse_conditions("jab RSI 70 se upar ho to sell karo")
    compares = [c for c in conds if c.type == "indicator_compare"]
    assert len(compares) == 1
    assert compares[0].op == ">"
    assert compares[0].value == 70.0


def test_english_word_order_still_works_unchanged():
    """The original, already-working order must not regress."""
    conds = parse_conditions("RSI below 30")
    compares = [c for c in conds if c.type == "indicator_compare"]
    assert len(compares) == 1
    assert compares[0].op == "<"
    assert compares[0].value == 30.0


def test_a_genuinely_mixed_language_document_end_to_end():
    """A realistic mixed English/Roman Urdu/slang paste -- multiple lines,
    multiple phrasing styles in the same document."""
    text = (
        "Entry: RSI 30 se neeche jaye to buy karo.\n"
        "Exit: jab RSI 70 se upar ho to sell karo.\n"
        "Stop loss 1.5%. Take profit risk reward 2:1.\n"
    )
    lines = [l for l in text.splitlines() if l.strip()]
    entry_conds = parse_conditions(lines[0].replace("Entry:", ""))
    exit_conds = parse_conditions(lines[1].replace("Exit:", ""))
    assert any(c.type == "indicator_compare" and c.op == "<" and c.value == 30.0 for c in entry_conds)
    assert any(c.type == "indicator_compare" and c.op == ">" and c.value == 70.0 for c in exit_conds)


def test_known_remaining_gap_reversed_price_vs_indicator_still_degrades():
    """HONEST LIMITATION (Item 9 explicitly asks for this): 'close 50 EMA
    se upar' (price-vs-indicator in reversed Urdu order) is NOT yet
    understood -- it still falls back to a bare concept match, unlike the
    indicator-vs-number case fixed above. This test documents the gap so
    it can't silently regress into a false "fixed" claim, and gives future
    work a concrete failing case to start from."""
    conds = parse_conditions("close 50 EMA se upar hona chahiye")
    assert not any(c.type == "price_compare" for c in conds)


def test_known_remaining_gap_urdu_concept_phrasing_still_degrades():
    """HONEST LIMITATION: 'support ke neeche' (concept + Urdu postposition)
    is not specifically recognized as a directional support/resistance
    break -- still falls back to a generic concept match rather than a
    precise bearish support-break condition."""
    conds = parse_conditions("agar price support ke neeche chala jaye")
    assert conds and conds[0].type == "concept"  # understood as SOME concept, but not the precise directional one
