"""Batch 3, Task 1 -- Multi-Pass Extraction with Rule Counting.

Replaces a single combined AI extraction call (found in Batch 2 to
regularly drop most of a document's real rules -- PDH-PDL captured 2
conditions out of 6+ real rules) with:
  1. A rule-inventory call: list + count every distinct rule, no
     extraction at all.
  2. Three scope-restricted extraction passes (entry / exit+SL+TP /
     filters+risk), each told to ignore everything outside its scope.
  3. A comparison call: which inventory rules ended up genuinely
     represented in what the three passes captured.

~5 AI calls per import (1 + 3 + 1), all through the same provider
fallback chain and usage-logging path every other AI call in this
codebase uses (ai_integration.deep_understanding.call_provider_chain_generic).
The pre-import content-hash dedup cache (data_engine.storage.
get_ai_import_cache) still applies -- see importer.py's caller, which
checks the cache BEFORE calling into this module at all, so re-importing
an unchanged document never re-runs this whole chain.
"""

from datetime import datetime, timezone

from ai_integration import config as ai_config
from ai_integration import schema
from ai_integration.deep_understanding import call_provider_chain_generic
from ai_integration.fragment_merge import merge_fragment_additive

_COMPARISON_SYSTEM_PROMPT = (
    "You are a meticulous QA auditor for trading strategy extraction. "
    "You will be given a checklist of rules and a summary of what was "
    "captured. Respond with ONLY the requested JSON, no other text."
)


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _merge_list(*lists):
    out = []
    for lst in lists:
        for item in lst or []:
            if item not in out:
                out.append(item)
    return out


def _merge_scoped_strategies(entry_s, exit_s, filters_s):
    """entry_s/exit_s/filters_s: each a schema._clean_strategy()-shaped
    dict from one focused pass's "strategy" sub-dict, or None if that
    pass found nothing. Scopes are disjoint BY PROMPT DESIGN (each pass
    is told to leave every other field at its default), so merging is
    just "take whichever pass populated each field" -- no conflict
    resolution needed. Returns None only if all three passes found
    nothing at all."""
    entry_s = entry_s or {}
    exit_s = exit_s or {}
    filters_s = filters_s or {}
    if not entry_s and not exit_s and not filters_s:
        return None

    timeframes = {}
    for s in (entry_s, exit_s, filters_s):
        timeframes.update(s.get("timeframes") or {})

    indicators = []
    seen_ind = set()
    for s in (entry_s, exit_s, filters_s):
        for ind in s.get("indicators") or []:
            key = (ind.get("name"), ind.get("role"))
            if key not in seen_ind:
                seen_ind.add(key)
                indicators.append(ind)

    # The filters pass may legitimately place a candle_range_pct-type
    # filter condition inside entry_conditions (it IS an entry-gating
    # condition, just a filter-shaped one) -- union with the entry pass's
    # own conditions rather than picking one side.
    return {
        "name": entry_s.get("name") or exit_s.get("name") or filters_s.get("name") or "",
        "timeframes": timeframes,
        "indicators": indicators,
        "concepts_used": _merge_list(entry_s.get("concepts_used"), exit_s.get("concepts_used"), filters_s.get("concepts_used")),
        "entry_conditions": _merge_list(entry_s.get("entry_conditions"), filters_s.get("entry_conditions")),
        "long_entry_conditions": _merge_list(entry_s.get("long_entry_conditions"), filters_s.get("long_entry_conditions")),
        "short_entry_conditions": _merge_list(entry_s.get("short_entry_conditions"), filters_s.get("short_entry_conditions")),
        "entry_rule_groups": entry_s.get("entry_rule_groups") or [],
        "exit_conditions": exit_s.get("exit_conditions") or [],
        "confirmation_conditions": exit_s.get("confirmation_conditions") or [],
        "stop_loss": exit_s.get("stop_loss") or {"type": "unknown", "value": None, "level": None},
        "take_profit": exit_s.get("take_profit") or {"type": "unknown", "value": None, "level": None},
        "risk_pct": filters_s.get("risk_pct"),
        "risk_reward": exit_s.get("risk_reward") if exit_s.get("risk_reward") is not None else filters_s.get("risk_reward"),
        "session_filter": filters_s.get("session_filter") or [],
        "trend_filter": filters_s.get("trend_filter"),
        "day_filter": filters_s.get("day_filter") or [],
        "breakeven_at_rr": exit_s.get("breakeven_at_rr"),
        "entry_type": entry_s.get("entry_type") or "market",
        "entry_price_offset_pct": entry_s.get("entry_price_offset_pct"),
        "sl_distance_filter_pct": filters_s.get("sl_distance_filter_pct"),
        "min_risk_reward_filter": filters_s.get("min_risk_reward_filter"),
        "primary_target_lookback_bars": filters_s.get("primary_target_lookback_bars"),
        "partial_take_profit": filters_s.get("partial_take_profit"),
    }


def _describe_captured_strategy(strategy):
    """Plain-text summary of a merged strategy dict for the comparison
    call to judge against -- cheaper and easier for the model to reason
    over than raw JSON, and doesn't require it to understand this
    codebase's field names."""
    if not strategy:
        return "Nothing was captured at all -- no strategy fields were populated."

    def _fmt_cond(c):
        if c.get("type") == "concept":
            return f"{c.get('name')} ({c.get('direction') or 'either direction'})"
        if c.get("type") in ("indicator_compare", "price_compare"):
            return f"{c.get('indicator')} {c.get('op')} {c.get('value')}"
        if c.get("type") == "candle_range_pct":
            p = c.get("params") or {}
            return f"candle range between {p.get('min_pct')}% and {p.get('max_pct')}%"
        if c.get("type") == "session":
            return f"session = {c.get('name')}"
        if c.get("type") == "trend":
            return f"trend = {c.get('direction')}"
        if c.get("type") == "raw":
            return f"unrecognized/raw: {c.get('text')}"
        return str(c)

    lines = []
    for key in ("entry_conditions", "long_entry_conditions", "short_entry_conditions"):
        conds = strategy.get(key) or []
        if conds:
            lines.append(f"{key}: " + "; ".join(_fmt_cond(c) for c in conds))
    for g in strategy.get("entry_rule_groups") or []:
        lines.append(f"entry rule group '{g.get('label')}' ({g.get('direction')}): " +
                      "; ".join(_fmt_cond(c) for c in g.get("conditions") or []))
    for c in strategy.get("exit_conditions") or []:
        lines.append(f"exit condition: {_fmt_cond(c)}")
    sl, tp = strategy.get("stop_loss") or {}, strategy.get("take_profit") or {}
    if sl.get("type") and sl["type"] != "unknown":
        lines.append(f"stop_loss: type={sl['type']} value={sl.get('value')} level={sl.get('level')}")
    if tp.get("type") and tp["type"] != "unknown":
        lines.append(f"take_profit: type={tp['type']} value={tp.get('value')} level={tp.get('level')}")
    if strategy.get("breakeven_at_rr") is not None:
        lines.append(f"breakeven at {strategy['breakeven_at_rr']}R")
    if strategy.get("sl_distance_filter_pct"):
        lines.append(f"stop-loss distance filter: {strategy['sl_distance_filter_pct']}")
    if strategy.get("min_risk_reward_filter") is not None:
        lines.append(f"minimum risk:reward filter: {strategy['min_risk_reward_filter']} "
                      f"(against the {strategy.get('primary_target_lookback_bars')}-candle lookback target)")
    if strategy.get("partial_take_profit"):
        lines.append(f"partial take-profit: {strategy['partial_take_profit']}")
    if strategy.get("risk_pct") is not None:
        lines.append(f"risk per trade: {strategy['risk_pct']}%")
    if strategy.get("risk_reward") is not None:
        lines.append(f"risk:reward: {strategy['risk_reward']}")
    if strategy.get("session_filter"):
        lines.append(f"session filter: {strategy['session_filter']}")
    if strategy.get("day_filter"):
        lines.append(f"day filter: {strategy['day_filter']}")
    if strategy.get("trend_filter"):
        lines.append(f"trend filter: {strategy['trend_filter']}")
    if strategy.get("entry_type") and strategy["entry_type"] != "market":
        lines.append(f"entry fills via: {strategy['entry_type']}")
    return "\n".join(lines) if lines else "Nothing was captured at all -- no strategy fields were populated."


def run_multi_pass_extraction(raw_text, source_hint=None, content_type=None):
    """Never raises. Returns:
    {
      "result": {...same shape as schema.parse_structured_response()...} or None,
      "provider": str or None (last provider that answered successfully),
      "call_count": int,
      "rule_inventory": {"rules": [...], "count": int},
      "comparison": {"expected_count": int, "captured_count": int,
                      "rules": [{"id","text","category","status","captured_as"}]},
      "error": str or None,
    }"""
    chain = ai_config.provider_fallback_chain()
    if not chain:
        return {
            "result": None, "provider": None, "call_count": 0,
            "rule_inventory": {"rules": [], "count": 0},
            "comparison": {"expected_count": 0, "captured_count": 0, "rules": []},
            "error": None,
        }

    call_count = 0
    last_provider = None

    # ---- Step 1: rule inventory (count + list, no extraction) ----
    inv_prompt = schema.build_rule_inventory_prompt()
    inventory, inv_provider, inv_err = call_provider_chain_generic(
        raw_text, chain, inv_prompt, "/ai/import/rule-inventory", schema.parse_rule_inventory_response,
    )
    call_count += 1
    if inv_provider:
        last_provider = inv_provider
    if inventory is None:
        inventory = {"rules": [], "count": 0}

    # ---- Step 2: three scope-restricted extraction passes ----
    scoped = {}
    pass_errors = []
    for scope in schema.RULE_CATEGORIES:
        prompt = schema.build_scoped_extraction_prompt(scope, source_hint, content_type)
        parsed, provider_name, err = call_provider_chain_generic(
            raw_text, chain, prompt, f"/ai/import/scoped-extraction-{scope}", schema.parse_structured_response,
        )
        call_count += 1
        scoped[scope] = parsed
        if provider_name:
            last_provider = provider_name
        if parsed is None:
            pass_errors.append(f"{scope} pass: {err}")

    strategies = [(scoped[s] or {}).get("strategy") for s in schema.RULE_CATEGORIES]
    merged_strategy = _merge_scoped_strategies(*strategies)

    all_lessons, all_terms, all_fields, all_missing, all_psych, confidences = [], [], [], [], [], []
    for scope in schema.RULE_CATEGORIES:
        r = scoped[scope]
        if not r:
            continue
        all_lessons.extend(r.get("lessons") or [])
        all_terms.extend(r.get("dictionary_terms") or [])
        all_fields.extend(r.get("inferred_fields") or [])
        all_missing.extend(r.get("missing_rules") or [])
        all_psych.extend(r.get("psychology_notes") or [])
        confidences.append(r.get("confidence", 0))

    result = {
        "confidence": min(confidences) if confidences else 0,
        "strategy": merged_strategy,
        "lessons": all_lessons,
        "dictionary_terms": all_terms,
        "inferred_fields": all_fields,
        "missing_rules": all_missing,
        "psychology_notes": all_psych,
    }

    # ---- Step 3: comparison -- which checklist rules are genuinely captured ----
    comparison = {"expected_count": inventory["count"], "captured_count": 0, "rules": []}
    if inventory["rules"]:
        captured_summary = _describe_captured_strategy(merged_strategy)
        cmp_content = schema.build_comparison_prompt(inventory, captured_summary)
        cmp_parsed, cmp_provider, cmp_err = call_provider_chain_generic(
            cmp_content, chain, _COMPARISON_SYSTEM_PROMPT, "/ai/import/extraction-comparison",
            schema.parse_comparison_response,
        )
        call_count += 1
        if cmp_provider:
            last_provider = cmp_provider

        status_by_id = {r["rule_id"]: r for r in (cmp_parsed or {}).get("results", [])} if cmp_parsed else {}
        for rule in inventory["rules"]:
            match = status_by_id.get(rule["id"])
            # A comparison call that failed entirely (cmp_parsed is None)
            # must never be silently read as "everything captured" --
            # marked "unknown" instead, distinct from a genuine "missing"
            # verdict the AI actually gave.
            if cmp_parsed is None:
                status, captured_as = "unknown", None
            elif match:
                status, captured_as = match["status"], match["captured_as"]
            else:
                status, captured_as = "missing", None
            if status == "captured":
                comparison["captured_count"] += 1
            comparison["rules"].append({**rule, "status": status, "captured_as": captured_as})

    error = "; ".join(pass_errors) if (merged_strategy is None and pass_errors) else None
    return {
        "result": result, "provider": last_provider, "call_count": call_count,
        "rule_inventory": inventory, "comparison": comparison, "error": error,
    }


# ================================================================
# Batch 3, Task 2: Auto-Retry for Missing Rules
# ================================================================

MAX_RETRIES = 3


def _merge_retry_fragment(existing, fragment):
    """Merges a targeted retry pass's recovered fields INTO the
    already-captured strategy -- additive only, never overwrites a field
    an earlier pass already resolved. Thin wrapper over the shared
    ai_integration.fragment_merge logic (Batch 5, Task 1 -- also used by
    sentence_level_extraction to merge one fragment per statement)."""
    return merge_fragment_additive(existing, fragment)


def run_multi_pass_extraction_with_retry(raw_text, source_hint=None, content_type=None, max_retries=MAX_RETRIES):
    """Runs run_multi_pass_extraction() once, then -- if the comparison
    shows any missing/unknown rules -- issues up to `max_retries`
    targeted follow-up calls, each naming only the rules still missing
    and their exact original text (schema.build_retry_prompt), re-running
    the comparison after each attempt. Stops as soon as everything is
    captured, or after max_retries regardless. Never fabricates: a rule
    still missing after every retry stays recorded as "missing" with its
    original text intact (see extraction_fidelity_reports) -- this
    function only ever adds genuinely-recovered fields, never invents a
    substitute to make the numbers match.

    Returns the same shape as run_multi_pass_extraction(), plus
    "retry_count" (int, 0 if nothing was missing after the first pass)."""
    base = run_multi_pass_extraction(raw_text, source_hint, content_type)
    total_calls = base["call_count"]
    provider = base["provider"]
    strategy = (base["result"] or {}).get("strategy")
    comparison = base["comparison"]
    retry_count = 0

    while retry_count < max_retries:
        missing = [
            {"id": r["id"], "text": r["text"], "category": r["category"]}
            for r in comparison["rules"] if r["status"] in ("missing", "unknown")
        ]
        if not missing:
            break
        chain = ai_config.provider_fallback_chain()
        if not chain:
            break
        retry_count += 1

        retry_prompt = schema.build_retry_prompt(missing, source_hint, content_type)
        parsed, provider_name, _err = call_provider_chain_generic(
            raw_text, chain, retry_prompt, f"/ai/import/retry-{retry_count}", schema.parse_structured_response,
        )
        total_calls += 1
        if provider_name:
            provider = provider_name
        strategy = _merge_retry_fragment(strategy, (parsed or {}).get("strategy"))

        captured_summary = _describe_captured_strategy(strategy)
        cmp_content = schema.build_comparison_prompt({"rules": comparison["rules"]}, captured_summary)
        cmp_parsed, cmp_provider, _cmp_err = call_provider_chain_generic(
            cmp_content, chain, _COMPARISON_SYSTEM_PROMPT, f"/ai/import/extraction-comparison-retry-{retry_count}",
            schema.parse_comparison_response,
        )
        total_calls += 1
        if cmp_provider:
            provider = cmp_provider

        status_by_id = {r["rule_id"]: r for r in (cmp_parsed or {}).get("results", [])} if cmp_parsed else {}
        new_rules, captured_count = [], 0
        for rule in comparison["rules"]:
            if rule["status"] == "captured":
                new_rules.append(rule)
                captured_count += 1
                continue
            if cmp_parsed is None:
                # This retry's comparison call itself failed -- keep the
                # rule's previous status rather than silently downgrading
                # or upgrading it based on no information.
                new_rules.append(rule)
                continue
            match = status_by_id.get(rule["id"])
            status, captured_as = (match["status"], match["captured_as"]) if match else ("missing", None)
            if status == "captured":
                captured_count += 1
            new_rules.append({"id": rule["id"], "text": rule["text"], "category": rule["category"],
                               "status": status, "captured_as": captured_as})
        comparison = {"expected_count": comparison["expected_count"], "captured_count": captured_count, "rules": new_rules}

    result = None
    if base["result"] is not None:
        result = dict(base["result"])
        result["strategy"] = strategy

    return {
        "result": result, "provider": provider, "call_count": total_calls,
        "rule_inventory": base["rule_inventory"], "comparison": comparison,
        "retry_count": retry_count, "error": base["error"],
    }
