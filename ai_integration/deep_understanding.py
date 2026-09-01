"""AI Knowledge Learning Engine (v7) -- AI-Native Structured Extraction.
For each document (or chunk), ONE AI call directly produces a
StrategyConfig/Lesson-shaped JSON structure (using only the backtest
engine's real executable vocabulary) plus hidden/inferred-field metadata,
new dictionary terms, and psychology notes. ai_integration.strategy_builder
turns the strategy/lesson dicts into real objects -- nothing here, and
nothing downstream of a successful AI call, ever routes through the old
regex-based rule_extractor/strategy_parser/lesson_extractor pipeline. That
pipeline is reserved entirely for when AI is disabled or every provider in
the fallback chain fails (Offline Mode).

Smart Provider Switching (Claude -> Groq -> OpenAI -> Gemini -> DeepSeek ->
Offline Mode) is unchanged from earlier phases.
"""

from datetime import datetime, timezone

from data_engine import storage

from ai_integration import chunking
from ai_integration import config as ai_config
from ai_integration import providers as ai_providers
from ai_integration import schema


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


# Shown whenever AI extraction is switched ON but no provider is actually
# usable (none enabled, or the enabled one has no API key). Deliberately
# names the cause and the fix -- an empty provider chain used to return
# error=None, which every caller then read as "the AI ran and found
# nothing", silently degrading to offline rule-based parsing.
NO_PROVIDER_ERROR = (
    "No usable AI provider is configured (a provider must be both enabled AND "
    "have an API key) -- falling back to offline rule-based parsing. "
    "Check the AI provider settings."
)


def call_provider_chain_generic(text, chain, system_prompt, endpoint_label, parse_fn):
    """(Batch 3, Task 1) The shared provider-fallback-with-logging loop
    behind every single AI call this module makes -- used directly by
    _call_provider_chain below (the original single-pass structured
    extraction) and by ai_integration.multi_pass_extraction's rule-count/
    scoped-pass/comparison calls, so there is exactly one place that
    tries providers in order, logs usage, and turns provider text into a
    parsed result (or a clear error) rather than three slightly different
    copies of the same loop.

    parse_fn(raw_text) -> parsed_or_None (never raises; return None for
    "not usable"). Returns (parsed_or_None, provider_name_or_None,
    error_summary_or_None). Never raises."""
    attempts = []
    for provider_name in chain:
        try:
            settings = ai_config.get_provider_settings(provider_name)
            provider = ai_providers.get_provider(provider_name, settings)
            result = provider.chat(text, system=system_prompt)
            storage.save_ai_usage_log(
                provider_name, settings.get("model"), endpoint_label,
                "success" if result.ok else "error", _now_iso(),
                tokens_in=result.tokens_in, tokens_out=result.tokens_out, latency_ms=result.latency_ms,
                error_message=None if result.ok else result.error,
            )
            if result.ok and result.text.strip():
                parsed = parse_fn(result.text)
                if parsed is not None:
                    return parsed, provider_name, None
                attempts.append(f"{provider_name}: response was not valid/usable JSON")
                continue
            attempts.append(f"{provider_name}: {result.error or 'no usable text returned'}")
        except Exception as exc:  # pragma: no cover -- defensive, must never crash the import
            attempts.append(f"{provider_name}: {exc}")
            try:
                storage.save_ai_usage_log(
                    provider_name, None, endpoint_label, "error", _now_iso(), error_message=str(exc)
                )
            except Exception:
                pass
    return None, None, "; ".join(attempts) if attempts else "no provider attempted"


def _call_provider_chain(text, chain, source_hint, content_type=None):
    """One structured-extraction attempt over a single piece of text (the
    whole document, or one chunk of it), trying each provider in `chain` in
    order. Returns (parsed_dict_or_None, provider_name_or_None,
    error_summary_or_None). Never raises."""
    system_prompt = schema.build_structured_extraction_prompt(source_hint, content_type)
    return call_provider_chain_generic(
        text, chain, system_prompt, "/ai/import/structured-extraction", schema.parse_structured_response,
    )


def _dedupe_str_list(items):
    seen = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen


def _merge_dictionary_terms(all_terms):
    merged = {}
    for term in all_terms:
        key = term["term"].strip().lower()
        if key not in merged:
            merged[key] = term
    return list(merged.values())


def _merge_inferred_fields(all_fields):
    merged = {}
    for f in all_fields:
        key = f["field"].strip().lower()
        if key not in merged or f["confidence"] > merged[key]["confidence"]:
            merged[key] = f
    return list(merged.values())


def _merge_lessons(all_lessons):
    merged = {}
    for lesson in all_lessons:
        key = lesson["description"].strip().lower()
        if key not in merged:
            merged[key] = lesson
    return list(merged.values())


def _condition_key(c):
    return (c.get("type"), c.get("indicator"), c.get("name"), c.get("op"), c.get("value"), c.get("direction"), c.get("text"))


def _merge_conditions(all_conditions):
    seen = set()
    merged = []
    for c in all_conditions:
        key = _condition_key(c)
        if key in seen:
            continue
        seen.add(key)
        merged.append(c)
    return merged


def _merge_strategies(strategies):
    """strategies: list of non-None "strategy" dicts, one per chunk that
    detected one, in chunk order. A stop_loss/take_profit/risk value is
    normally stated once in a document, not per-chunk -- the first chunk
    that actually resolved it wins rather than the last, so a later chunk
    that legitimately had nothing to say about it can't blank out an
    earlier finding."""
    if not strategies:
        return None
    merged = {
        "name": next((s.get("name") for s in strategies if s.get("name")), ""),
        "timeframes": {}, "indicators": [], "concepts_used": [],
        "entry_conditions": [], "exit_conditions": [], "confirmation_conditions": [],
        "stop_loss": {"type": "unknown", "value": None, "level": None},
        "take_profit": {"type": "unknown", "value": None, "level": None},
        "risk_pct": None, "risk_reward": None,
        "session_filter": [], "trend_filter": None,
    }
    for s in strategies:
        merged["timeframes"].update(s.get("timeframes") or {})
        for ind in s.get("indicators") or []:
            if ind not in merged["indicators"]:
                merged["indicators"].append(ind)
        for c in s.get("concepts_used") or []:
            if c not in merged["concepts_used"]:
                merged["concepts_used"].append(c)
        merged["entry_conditions"].extend(s.get("entry_conditions") or [])
        merged["exit_conditions"].extend(s.get("exit_conditions") or [])
        merged["confirmation_conditions"].extend(s.get("confirmation_conditions") or [])
        if merged["stop_loss"]["type"] == "unknown" and (s.get("stop_loss") or {}).get("type", "unknown") != "unknown":
            merged["stop_loss"] = s["stop_loss"]
        if merged["take_profit"]["type"] == "unknown" and (s.get("take_profit") or {}).get("type", "unknown") != "unknown":
            merged["take_profit"] = s["take_profit"]
        if merged["risk_pct"] is None and s.get("risk_pct") is not None:
            merged["risk_pct"] = s["risk_pct"]
        if merged["risk_reward"] is None and s.get("risk_reward") is not None:
            merged["risk_reward"] = s["risk_reward"]
        for sess in s.get("session_filter") or []:
            if sess not in merged["session_filter"]:
                merged["session_filter"].append(sess)
        if merged["trend_filter"] is None and s.get("trend_filter"):
            merged["trend_filter"] = s["trend_filter"]

    merged["entry_conditions"] = _merge_conditions(merged["entry_conditions"])
    merged["exit_conditions"] = _merge_conditions(merged["exit_conditions"])
    merged["confirmation_conditions"] = _merge_conditions(merged["confirmation_conditions"])
    return merged


def understand_document_structured(raw_text, use_ai, source_hint=None, content_type=None):
    """The single AI-Native Structured Extraction entry point. Returns:
    {"result": {...schema.parse_structured_response() shape...} or None,
     "provider": str or None, "error": str or None}.
    result is None whenever AI is disabled/unconfigured/every provider
    failed on every chunk -- callers fall back to the old deterministic
    compile_document() pipeline (Offline Mode), never a crash.

    AI Usage Policy: one structured-extraction call per document, UNLESS the
    document exceeds the practical per-call context window, in which case it
    is chunked and one call is made per chunk (each chunk understood
    independently, then merged below into ONE strategy + ONE unioned set of
    lesson/dictionary/inferred-field/missing-rule/psychology findings, with
    confidence taken as the minimum across chunks -- conservative, since one
    poorly-understood chunk should pull down overall trust)."""
    if not use_ai:
        return {"result": None, "provider": None, "error": None}

    chain = ai_config.provider_fallback_chain()
    if not chain:
        # Was `"error": None` -- indistinguishable from "the AI ran and
        # genuinely found nothing", so a misconfigured/expired key made
        # every import silently fall back to offline rule-based parsing
        # with nothing anywhere saying why. `use_ai=False` above stays
        # silent on purpose (the CEO deliberately turned AI off; that is
        # a choice, not a failure) -- this branch is a real
        # misconfiguration and must say so. Callers already surface it:
        # sindhu_web/api/ai_integration.py raises HTTPException(422,
        # result["error"]) and import_queue marks the item failed with it.
        return {"result": None, "provider": None, "error": NO_PROVIDER_ERROR}

    if not chunking.needs_chunking(raw_text):
        parsed, provider_name, error = _call_provider_chain(raw_text, chain, source_hint, content_type)
        if parsed is not None:
            return {"result": parsed, "provider": provider_name, "error": None}
        return {
            "result": None, "provider": None,
            "error": f"All AI providers failed ({error}); used rule-based parsing.",
        }

    chunks = chunking.split_into_chunks(raw_text)
    strategies, all_lessons, all_dictionary_terms = [], [], []
    all_inferred_fields, all_missing_rules, all_psychology_notes = [], [], []
    confidences = []
    succeeded_provider = None
    failed_chunks = 0

    for chunk in chunks:
        parsed, provider_name, error = _call_provider_chain(chunk, chain, source_hint, content_type)
        if parsed is not None:
            if parsed.get("strategy"):
                strategies.append(parsed["strategy"])
            all_lessons.extend(parsed["lessons"])
            all_dictionary_terms.extend(parsed["dictionary_terms"])
            all_inferred_fields.extend(parsed["inferred_fields"])
            all_missing_rules.extend(parsed["missing_rules"])
            all_psychology_notes.extend(parsed["psychology_notes"])
            confidences.append(parsed["confidence"])
            succeeded_provider = succeeded_provider or provider_name
        else:
            failed_chunks += 1

    if succeeded_provider is None:
        return {
            "result": None, "provider": None,
            "error": f"All AI providers failed on every one of {len(chunks)} chunks; used rule-based parsing.",
        }

    merged = {
        "confidence": min(confidences) if confidences else 0,
        "strategy": _merge_strategies(strategies),
        "lessons": _merge_lessons(all_lessons),
        "dictionary_terms": _merge_dictionary_terms(all_dictionary_terms),
        "inferred_fields": _merge_inferred_fields(all_inferred_fields),
        "missing_rules": _dedupe_str_list(all_missing_rules),
        "psychology_notes": _dedupe_str_list(all_psychology_notes),
    }
    note = None
    if failed_chunks:
        note = (
            f"AI understood {len(chunks) - failed_chunks}/{len(chunks)} chunks (used '{succeeded_provider}'); "
            f"{failed_chunks} chunk(s) contributed nothing after every provider failed on them."
        )
    return {"result": merged, "provider": succeeded_provider, "error": note}
