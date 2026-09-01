"""Extraction Pipeline Improvements (Step 3, Part A) -- regression tests
for three confirmed gaps found during Fabio Valentina's Models end-to-end
verification:

  Gap 1: a document describing 2+ distinct trading models was merged into
         one generic setup instead of captured as separate rule-sets.
  Gap 2: session-scoping language ("New York session only") was silently
         dropped instead of populating session_filter.
  Gap 3: a concept outside SINDHU's vocabulary (e.g. "Low Volume Node")
         was silently substituted with an unrelated known concept instead
         of being honestly flagged as unmapped.

Mocked AI calls throughout (no network) -- these test the deterministic
pre-processing (heading/model detection, prompt content, merge logic) and
the orchestration around AI responses, not live AI judgment itself (which
can't be asserted on deterministically). Prompt-content assertions are
explicitly a narrower guarantee than full behavioral proof; see the final
report for that caveat.
"""

from unittest.mock import patch

from ai_integration import sentence_level_extraction as sle
from ai_integration import schema
from ai_integration.deterministic_rules import detect_model_sections, split_into_statements_with_labels
from ai_integration.fragment_merge import _merge_entry_rule_groups, merge_fragment_additive
from ai_integration.strategy_builder import build_condition


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


TWO_MODEL_DOC = """### Model 1: Trend Following
If price closes above PDH, buy the breakout.
Stop loss is 0.3% below entry.

### Model 2: Mean Reversion
If price sweeps below PDL and closes back above it, buy the reversal.
Stop loss is 0.5% below the sweep low.
"""

AMBIGUOUS_DOC = """This document covers Model 1 and Model 2 loosely.
If price closes above PDH, buy the breakout.
Model 2 uses a similar idea but mean-reverting instead.
"""

SINGLE_MODEL_DOC = "If price closes above PDH, buy.\nStop loss is 0.3% below entry."


# ------------------------------------------------------------ Gap 1: multi-model detection

def test_two_clear_model_headings_detected_confidently():
    sections = detect_model_sections(TWO_MODEL_DOC)
    assert len(sections["labels"]) == 2
    assert sections["ambiguous"] is False
    assert "Model 1" in sections["labels"][0]
    assert "Model 2" in sections["labels"][1]


def test_single_model_document_gets_no_labels_at_all():
    sections = detect_model_sections(SINGLE_MODEL_DOC)
    assert sections["labels"] == []
    assert sections["ambiguous"] is False


def test_ambiguous_multi_model_mentions_without_clean_headings_are_flagged_not_guessed():
    sections = detect_model_sections(AMBIGUOUS_DOC)
    assert sections["labels"] == []  # no confident heading-based split
    assert sections["ambiguous"] is True
    assert sections["reason"]  # non-empty explanation, not silently dropped


def test_statements_are_labeled_with_their_model_section():
    labeled = split_into_statements_with_labels(TWO_MODEL_DOC)
    by_text = {text: model_label for text, model_label, _section_label in labeled}
    pdh_stmt = next(t for t in by_text if "PDH" in t)
    pdl_stmt = next(t for t in by_text if "PDL" in t)
    assert "Model 1" in by_text[pdh_stmt]
    assert "Model 2" in by_text[pdl_stmt]
    assert by_text[pdh_stmt] != by_text[pdl_stmt]


def test_single_model_document_statements_have_no_model_label():
    labeled = split_into_statements_with_labels(SINGLE_MODEL_DOC)
    assert all(model_label is None for _, model_label, _section_label in labeled)


def test_merge_entry_rule_groups_unions_by_label_not_first_wins():
    """Regression for the exact bug found: entry_rule_groups used to keep
    only the FIRST fragment's groups, silently discarding every later
    fragment's groups -- the root mechanism behind two models collapsing
    into one."""
    existing = [{"label": "Model 1 (long)", "direction": "bullish", "conditions": ["A"]}]
    new = [{"label": "Model 2 (long)", "direction": "bullish", "conditions": ["B"]}]
    merged = _merge_entry_rule_groups(existing, new)
    assert len(merged) == 2  # both models kept as separate groups, not clobbered
    labels = [g["label"] for g in merged]
    assert "Model 1 (long)" in labels and "Model 2 (long)" in labels


def test_merge_entry_rule_groups_unions_conditions_within_same_label():
    existing = [{"label": "Model 1 (long)", "direction": "bullish", "conditions": ["A"]}]
    new = [{"label": "Model 1 (long)", "direction": "bullish", "conditions": ["B"]}]
    merged = _merge_entry_rule_groups(existing, new)
    assert len(merged) == 1
    assert merged[0]["conditions"] == ["A", "B"]


def test_sentence_level_extraction_keeps_two_models_as_separate_entry_rule_groups():
    """End-to-end (mocked AI) proof of the actual fix: a document with two
    labeled models produces TWO distinct entry_rule_groups, not one merged
    flat entry_conditions list."""
    def fake_call(statement_text, chain, prompt, endpoint, parse_fn):
        if "PDH" in statement_text:
            return {"is_rule": True, "strategy": _strategy_fragment(
                long_entry_conditions=[{"type": "concept", "name": "pdh", "direction": "bullish"}],
            )}, "groq", None
        if "PDL" in statement_text:
            return {"is_rule": True, "strategy": _strategy_fragment(
                long_entry_conditions=[{"type": "concept", "name": "pdl", "direction": "bullish"}],
            )}, "groq", None
        return {"is_rule": True, "strategy": _strategy_fragment()}, "groq", None

    with patch.object(sle, "call_provider_chain_generic", side_effect=fake_call), \
         patch("ai_integration.config.provider_fallback_chain", return_value=["groq"]):
        result = sle.run_sentence_level_extraction(TWO_MODEL_DOC)

    strategy = result["result"]["strategy"]
    groups = strategy["entry_rule_groups"]
    labels = [g["label"] for g in groups]
    assert any("Model 1" in l for l in labels)
    assert any("Model 2" in l for l in labels)
    # The flat lists must NOT also contain these conditions -- otherwise
    # gap 1 is only half-fixed (present in both places = still merged).
    assert strategy["long_entry_conditions"] == []
    assert result["model_sections"]["ambiguous"] is False


def test_model_label_is_passed_as_context_to_the_ai_call():
    seen = []

    def fake_call(statement_text, chain, prompt, endpoint, parse_fn):
        seen.append(statement_text)
        return {"is_rule": True, "strategy": _strategy_fragment()}, "groq", None

    with patch.object(sle, "call_provider_chain_generic", side_effect=fake_call), \
         patch("ai_integration.config.provider_fallback_chain", return_value=["groq"]):
        sle.run_sentence_level_extraction(TWO_MODEL_DOC)

    assert any("[This statement is part of: Model 1" in s for s in seen)
    assert any("[This statement is part of: Model 2" in s for s in seen)


# ------------------------------------------------------------ Gap 2: session filter capture

def test_statement_prompt_gives_explicit_session_phrasing_examples():
    prompt = schema.build_statement_extraction_prompt()
    assert "session_filter" in prompt
    assert "New York session" in prompt or "NY session" in prompt
    assert "London" in prompt


def test_whole_doc_prompt_gives_explicit_session_phrasing_examples():
    prompt = schema.build_structured_extraction_prompt()
    assert "session-scoping" in prompt or "session_filter" in prompt
    assert "New York session" in prompt or "NY session" in prompt


def test_session_filter_fragment_flows_through_to_final_strategy():
    """Plumbing check: when a statement's AI response DOES correctly
    populate session_filter, it survives all the way to the merged
    result (not dropped by additive merge or _clean_strategy filtering)."""
    def fake_call(statement_text, chain, prompt, endpoint, parse_fn):
        return {"is_rule": True, "strategy": _strategy_fragment(session_filter=["ny"])}, "groq", None

    with patch.object(sle, "call_provider_chain_generic", side_effect=fake_call), \
         patch("ai_integration.config.provider_fallback_chain", return_value=["groq"]):
        result = sle.run_sentence_level_extraction("Only trade during the New York session.")

    assert result["result"]["strategy"]["session_filter"] == ["ny"]


# ------------------------------------------------------------ Gap 3: no silent substitution

def test_statement_prompt_explicitly_forbids_mechanism_substitution():
    prompt = schema.build_statement_extraction_prompt()
    assert "DO NOT SUBSTITUTE" in prompt
    assert "Low Volume Node" in prompt
    assert "Order Flow Aggression" in prompt


def test_statement_prompt_maps_known_volume_profile_equivalents():
    prompt = schema.build_statement_extraction_prompt()
    assert '"lvn"' in prompt
    assert '"poc"' in prompt
    assert '"aggression"' in prompt


def test_unknown_concept_name_is_demoted_to_raw_not_accepted():
    """Code-level safety net (already existed, verified here explicitly
    for this task): an indicator/concept name the AI invents outside
    KNOWN_INDICATORS can never become a real, silently-wrong Condition --
    it is always demoted to raw with the original text preserved."""
    cond = build_condition({"type": "concept", "name": "footprint_imbalance", "direction": "bullish"})
    assert cond.type == "raw"
    assert "footprint_imbalance" in cond.text


def test_ai_choosing_a_known_but_unrelated_concept_is_not_caught_by_code_alone():
    """Honest boundary: if the AI ITSELF chooses a known-but-wrong concept
    (e.g. mapping a Low Volume Node to "support" instead of "lvn" or
    raw), no code-level check can catch that -- "support" is a valid,
    real concept name. This is exactly why the prompt-level anti-
    substitution instruction (tested above) is the actual fix for this
    half of gap 3, not a new code guard. Documented here so this
    limitation is explicit, not silently assumed away."""
    cond = build_condition({"type": "concept", "name": "support", "direction": "bullish"})
    assert cond.type == "concept"  # accepted -- "support" IS a real concept,
    assert cond.name == "support"  # code has no way to know this was a wrong guess


# ------------------------------------------------------------ synthetic document exercising all 3 gaps

ALL_THREE_GAPS_DOC = """### Model 1: Trend Following (New York Session)
Trades only during the New York session.
If price sweeps the previous day high (PDH) and closes back below it, sell the reversal.
Stop loss is placed above the Low Volume Node (LVN) that preceded the sweep.

### Model 2: Mean Reversion (London Session)
Trades only during the London session.
Enter long when price returns to the Point of Control (POC) of the prior balance area.
"""


def test_synthetic_document_exercising_all_three_gaps():
    """Constructs one document containing all three gap patterns (two
    distinct models, session-scoping per model, and both a mappable
    volume-profile concept (POC) and a concept requiring the LVN
    equivalent) and confirms the deterministic pre-processing correctly:
    (a) detects and separates the two models,
    (b) does not drop the session-scoping statements from the candidate
        list (they still reach the AI to have session_filter populated),
    (c) doesn't need to guess -- ambiguous is False since headings are
        clean.
    Gap 3's actual mapping decision (LVN/POC -> concept names) depends on
    live AI judgment guided by the now-strengthened prompt (tested above
    via prompt-content assertions), not asserted behaviorally here."""
    sections = detect_model_sections(ALL_THREE_GAPS_DOC)
    assert len(sections["labels"]) == 2
    assert sections["ambiguous"] is False

    labeled = split_into_statements_with_labels(ALL_THREE_GAPS_DOC)
    ny_stmt = next((t, m, s) for t, m, s in labeled if "New York session" in t)
    london_stmt = next((t, m, s) for t, m, s in labeled if "London session" in t)
    assert "Model 1" in ny_stmt[1]
    assert "Model 2" in london_stmt[1]
    assert ny_stmt[1] != london_stmt[1]

    # End-to-end with mocked AI: confirm session statements aren't
    # silently dropped as "not a rule" by the orchestration, and that
    # entry_rule_groups keep the two models apart.
    def fake_call(statement_text, chain, prompt, endpoint, parse_fn):
        if "New York session" in statement_text:
            return {"is_rule": True, "strategy": _strategy_fragment(session_filter=["ny"])}, "groq", None
        if "London session" in statement_text:
            return {"is_rule": True, "strategy": _strategy_fragment(session_filter=["london"])}, "groq", None
        if "previous day high" in statement_text:
            return {"is_rule": True, "strategy": _strategy_fragment(
                short_entry_conditions=[{"type": "concept", "name": "pdh_sweep", "direction": "bearish"}],
            )}, "groq", None
        if "Point of Control" in statement_text:
            return {"is_rule": True, "strategy": _strategy_fragment(
                long_entry_conditions=[{"type": "concept", "name": "poc", "direction": "bullish"}],
            )}, "groq", None
        if "Low Volume Node" in statement_text:
            # Correct behavior per the strengthened prompt: map to the real
            # equivalent ("lvn"), not force onto an unrelated concept.
            return {"is_rule": True, "strategy": _strategy_fragment(
                stop_loss={"type": "structure", "value": None, "level": None},
            )}, "groq", None
        return {"is_rule": True, "strategy": _strategy_fragment()}, "groq", None

    with patch.object(sle, "call_provider_chain_generic", side_effect=fake_call), \
         patch("ai_integration.config.provider_fallback_chain", return_value=["groq"]):
        result = sle.run_sentence_level_extraction(ALL_THREE_GAPS_DOC)

    strategy = result["result"]["strategy"]
    assert set(strategy["session_filter"]) == {"ny", "london"}
    labels = [g["label"] for g in strategy["entry_rule_groups"]]
    assert any("Model 1" in l for l in labels)
    assert any("Model 2" in l for l in labels)
    assert result["model_sections"]["ambiguous"] is False
