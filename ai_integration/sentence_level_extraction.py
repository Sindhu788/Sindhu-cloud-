"""Batch 5, Task 1 -- Sentence-Level Extraction with Retry Until
Reconciled. Replaces Batch 3's multi-pass approach (rule inventory + 3
scope-restricted whole-document passes) as the primary strategy
extraction pipeline.

Two changes from Batch 3, both aimed at the same measured failure (real
documents captured 0-9 of 14-24 real rules, and the SAME document varied
between runs -- 2/19 then 9/19 on identical text):

1. The "expected" checklist is now deterministic (ai_integration.
   deterministic_rules), not AI-generated -- so it never varies between
   runs on the same input, and costs zero tokens.
2. Extraction is now one small, narrowly-scoped AI call PER candidate
   statement (deterministically split out of the document), not a few
   large whole-document calls. A single isolated sentence is a much
   smaller, more answerable question than "find every rule in this
   whole document" -- that's where rules were being silently dropped.

Retry Until Reconciled: after the first pass over every candidate,
whatever's still unresolved (a call that failed/errored, or came back
unparseable) is retried with its exact original text, up to a limit.
Never fabricates -- a statement still unresolved after every retry stays
recorded as "missing" with its real original text, which the existing
Incomplete Lock (Batch 3, Task 3) already handles correctly.
"""

from ai_integration import config as ai_config
from ai_integration import schema
from ai_integration.deep_understanding import call_provider_chain_generic
from ai_integration.deterministic_rules import count_candidate_rules, detect_model_sections, extract_document_preambles
from ai_integration.fragment_merge import merge_fragment_additive

MAX_RETRIES = 3


def _context_prefix(model_label, section_label):
    """Extraction Pipeline Improvements (gap 1) + Two-Focused-Day Push
    (Part 1): builds the light, purely-informational context line
    prepended to an isolated statement before it's sent to the AI.

    model_label (a detected "Model N:" heading) and section_label (the
    nearest heading of ANY kind, e.g. "Short Entry (Sell)") are
    independent signals -- a document can have one, the other, both, or
    neither. Real-world documents like a single-model strategy split into
    "Entry Rules" / "Stop Loss Rules" / "Take Profit Rules" sections have
    ONLY a section_label, which previously got no context at all (that
    tracking only ever ran for 2+-model documents) -- this is the fix for
    an isolated statement like "place the SL slightly above the high
    created by the sweep" losing track of which section (and therefore
    which side of the trade) it belongs to.

    Neither label changes the schema or vocabulary; both are hints, never
    a routing decision (routing stays keyed on model_label alone, in
    _route_labeled_fragment)."""
    if model_label and section_label and section_label != model_label:
        return f"[This statement is part of: {model_label} > {section_label}]"
    if model_label:
        return f"[This statement is part of: {model_label}]"
    if section_label:
        return f"[This statement is under the section: {section_label}]"
    return None


def _call_one_statement(statement_text, prompt, chain, endpoint_label, model_label=None, section_label=None,
                         document_preamble=None):
    prefix = _context_prefix(model_label, section_label)
    text = statement_text if not prefix else f"{prefix}\n{statement_text}"
    if document_preamble:
        # Part 1 (Two-Focused-Day Push): the document's own opening/setup
        # content -- see deterministic_rules.extract_document_preamble --
        # so a statement that backward-references something defined
        # earlier ("the marked 4H high level") has a chance to resolve it.
        # Labeled distinctly from the statement itself so the AI never
        # mistakes preamble text for part of THIS statement to judge.
        text = f"[Document background, for context only -- not part of this statement: {document_preamble}]\n{text}"
    parsed, provider_name, err = call_provider_chain_generic(
        text, chain, prompt, endpoint_label, schema.parse_statement_response,
    )
    return parsed, provider_name, err


def _route_labeled_fragment(fragment, model_label):
    """When a statement belongs to a detected model/setup section, its
    conditions must land in that model's OWN entry_rule_groups entry, not
    the flat entry_conditions/long_entry_conditions/short_entry_conditions
    lists -- merging those flat lists across models is exactly gap 1 (two
    distinct trading models silently collapsed into one generic setup).
    Returns a new fragment dict with the flat entry-condition lists moved
    into labeled entry_rule_groups; every other field passes through
    unchanged (session_filter, stop_loss, exit_conditions, etc. are not
    model-specific structure the same way, and stay as-is)."""
    if not model_label:
        return fragment
    long_conds = fragment.get("long_entry_conditions") or []
    short_conds = fragment.get("short_entry_conditions") or []
    generic_conds = fragment.get("entry_conditions") or []
    if not (long_conds or short_conds or generic_conds):
        return fragment
    groups = []
    if long_conds:
        groups.append({"label": f"{model_label} (long)", "direction": "bullish", "conditions": long_conds})
    if short_conds:
        groups.append({"label": f"{model_label} (short)", "direction": "bearish", "conditions": short_conds})
    if generic_conds:
        groups.append({"label": model_label, "direction": None, "conditions": generic_conds})
    routed = dict(fragment)
    routed["long_entry_conditions"] = []
    routed["short_entry_conditions"] = []
    routed["entry_conditions"] = []
    routed["entry_rule_groups"] = groups
    return routed


def run_sentence_level_extraction(raw_text, source_hint=None, content_type=None, max_retries=MAX_RETRIES):
    """Never raises. Returns:
    {
      "result": {...same shape as schema.parse_structured_response()...} or None,
      "provider": str or None,
      "call_count": int,
      "rule_inventory": {"count": int, "candidates": [...]} (deterministic, from deterministic_rules),
      "comparison": {"expected_count": int, "captured_count": int,
                      "rules": [{"id","text","category","status","captured_as"}]},
      "retry_count": int,
      "error": str or None,
    }
    `category` in comparison["rules"] carries the deterministic signal
    group(s) (e.g. "entry_exit, numeric_or_timeframe") -- there is no
    AI-assigned entry/exit/filters category at this stage, unlike Batch
    3's inventory, since categorization is no longer needed to route the
    call (every statement gets its own call regardless of category)."""
    chain = ai_config.provider_fallback_chain()
    inventory = count_candidate_rules(raw_text)
    model_sections = detect_model_sections(raw_text)
    document_preambles = extract_document_preambles(raw_text)
    empty = {
        "result": None, "provider": None, "call_count": 0,
        "rule_inventory": inventory,
        "comparison": {"expected_count": inventory["count"], "captured_count": 0, "rules": []},
        "retry_count": 0, "error": None,
        "model_sections": model_sections,
    }
    if not chain or not inventory["candidates"]:
        return empty

    prompt = schema.build_statement_extraction_prompt(source_hint, content_type)
    call_count = 0
    last_provider = None
    merged_strategy = None
    rules = []  # [{"id","text","category","status","captured_as"}]
    pending_retry = []  # candidate dicts still unresolved after this pass

    for cand in inventory["candidates"]:
        model_label = cand.get("model_label")
        section_label = cand.get("section_label")
        parsed, provider_name, err = _call_one_statement(
            cand["text"], prompt, chain, f"/ai/import/statement-{cand['id']}", model_label, section_label,
            document_preambles.get(model_label, ""),
        )
        call_count += 1
        if provider_name:
            last_provider = provider_name
        category = ", ".join(cand["signals"])
        if parsed is None:
            rules.append({"id": cand["id"], "text": cand["text"], "category": category,
                           "status": "missing", "captured_as": None})
            pending_retry.append(cand)
            continue
        if not parsed["is_rule"]:
            # The AI disagrees with the deterministic heuristic that this
            # looked like a rule candidate -- resolved (not missing), just
            # correctly triaged as not-a-rule. Never counted as "captured"
            # (nothing was extracted), but never retried either.
            rules.append({"id": cand["id"], "text": cand["text"], "category": category,
                           "status": "not_a_rule", "captured_as": None})
            continue
        fragment = parsed["strategy"]
        if not fragment:
            # Said "is_rule: true" but produced no usable structured
            # fragment -- genuinely unresolved, worth a retry.
            rules.append({"id": cand["id"], "text": cand["text"], "category": category,
                           "status": "missing", "captured_as": None})
            pending_retry.append(cand)
            continue
        routed_fragment = _route_labeled_fragment(fragment, model_label)
        merged_strategy = merge_fragment_additive(merged_strategy, routed_fragment)
        rules.append({"id": cand["id"], "text": cand["text"], "category": category,
                       "status": "captured", "captured_as": _describe_fragment(fragment)})

    retry_count = 0
    while pending_retry and retry_count < max_retries:
        chain = ai_config.provider_fallback_chain()
        if not chain:
            break
        retry_count += 1
        still_pending = []
        for cand in pending_retry:
            model_label = cand.get("model_label")
            section_label = cand.get("section_label")
            parsed, provider_name, err = _call_one_statement(
                cand["text"], prompt, chain, f"/ai/import/statement-retry-{retry_count}-{cand['id']}",
                model_label, section_label, document_preambles.get(model_label, ""),
            )
            call_count += 1
            if provider_name:
                last_provider = provider_name
            idx = next(i for i, r in enumerate(rules) if r["id"] == cand["id"])
            if parsed is None:
                still_pending.append(cand)
                continue
            if not parsed["is_rule"]:
                rules[idx] = {**rules[idx], "status": "not_a_rule", "captured_as": None}
                continue
            fragment = parsed["strategy"]
            if not fragment:
                still_pending.append(cand)
                continue
            routed_fragment = _route_labeled_fragment(fragment, model_label)
            merged_strategy = merge_fragment_additive(merged_strategy, routed_fragment)
            rules[idx] = {**rules[idx], "status": "captured", "captured_as": _describe_fragment(fragment)}
        pending_retry = still_pending

    captured_count = sum(1 for r in rules if r["status"] == "captured")
    comparison = {"expected_count": inventory["count"], "captured_count": captured_count, "rules": rules}

    result = None
    if merged_strategy is not None:
        result = {
            "confidence": 100 if not pending_retry else 60,
            "strategy": merged_strategy,
            "lessons": [], "dictionary_terms": [], "inferred_fields": [],
            "missing_rules": [r["text"] for r in rules if r["status"] == "missing"],
            "psychology_notes": [],
        }

    error = None
    if merged_strategy is None and inventory["candidates"]:
        error = "No statement in this document produced a usable extraction after all retries."

    return {
        "result": result, "provider": last_provider, "call_count": call_count,
        "rule_inventory": inventory, "comparison": comparison,
        "retry_count": retry_count, "error": error,
        # Extraction Pipeline Improvements (gap 1): {"labels": [...], "ambiguous": bool,
        # "reason": str|None} -- callers (importer.py) route "ambiguous"
        # into the clarification flow instead of guessing a split.
        "model_sections": model_sections,
    }


def _describe_fragment(fragment):
    """One-line plain-English summary of what a single statement's
    fragment contributed -- shown as "captured_as" in the verification
    view, same spirit as multi_pass_extraction's comparison call, but
    computed locally (no extra AI call needed since we already know
    exactly which one statement produced this fragment)."""
    parts = []
    for key in ("entry_conditions", "long_entry_conditions", "short_entry_conditions", "exit_conditions"):
        for c in fragment.get(key) or []:
            parts.append(_fmt_condition(c))
    sl = fragment.get("stop_loss") or {}
    if sl.get("type") and sl["type"] != "unknown":
        parts.append(f"stop-loss: {sl['type']} {sl.get('value') if sl.get('value') is not None else sl.get('level')}")
    tp = fragment.get("take_profit") or {}
    if tp.get("type") and tp["type"] != "unknown":
        parts.append(f"take-profit: {tp['type']} {tp.get('value') if tp.get('value') is not None else tp.get('level')}")
    if fragment.get("risk_pct") is not None:
        parts.append(f"risk {fragment['risk_pct']}%")
    if fragment.get("risk_reward") is not None:
        parts.append(f"risk:reward {fragment['risk_reward']}")
    if fragment.get("session_filter"):
        parts.append(f"session: {', '.join(fragment['session_filter'])}")
    if fragment.get("sl_distance_filter_pct"):
        parts.append("stop-loss distance filter")
    if fragment.get("min_risk_reward_filter") is not None:
        parts.append(f"minimum R:R filter {fragment['min_risk_reward_filter']}")
    if fragment.get("partial_take_profit"):
        parts.append("partial take-profit")
    return "; ".join(parts) if parts else "mapped into strategy config"


def _fmt_condition(c):
    if c.get("type") == "concept":
        return f"{c.get('name')} ({c.get('direction') or 'either direction'})"
    if c.get("type") in ("indicator_compare", "price_compare"):
        return f"{c.get('indicator')} {c.get('op')} {c.get('value')}"
    if c.get("type") == "candle_range_pct":
        p = c.get("params") or {}
        return f"candle range {p.get('min_pct')}-{p.get('max_pct')}%"
    if c.get("type") == "raw":
        return f"unmapped: {c.get('text')}"
    return str(c)
