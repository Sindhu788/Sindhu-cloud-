"""AI Knowledge Learning Engine (v7) -- the JSON contract for AI-Native
Structured Extraction. This replaces the v6 design (AI reconstructs plain
text, which then gets fed back through the old regex-based rule_extractor/
strategy_parser). The CEO's explicit v7 directive: "Do NOT pass AI output
back into the old keyword parser. The old parser must ONLY be used when AI
is disabled."

So AI is now asked to directly produce a StrategyConfig-shaped and
Lesson-shaped structure -- entry/exit/confirmation conditions, stop loss,
take profit, risk, timeframes, sessions, lessons -- using ONLY the exact
indicator/concept/session/condition-type vocabulary the backtest engine
already knows how to execute (backtest_engine.validator._KNOWN_INDICATORS,
strategy_parser.SESSION_NAMES). ai_integration.strategy_builder is what
turns this validated dict into real StrategyConfig/Condition/Lesson objects
-- nothing here ever touches rule_extractor.py or strategy_parser.py.
"""

import json
import re

from knowledge_engine.lesson import CATEGORIES as LESSON_CATEGORIES

# Kept in sync with backtest_engine.validator._KNOWN_INDICATORS -- this is
# the complete vocabulary the backtest engine can actually evaluate. AI is
# constrained to only this vocabulary; strategy_builder.py demotes anything
# else to type="raw" (recognized as unexecutable, never silently guessed).
KNOWN_INDICATORS = [
    "ema", "sma", "vwap", "rsi", "macd", "atr", "volume",
    "support", "resistance", "bos", "choch", "fvg",
    "order_block", "breaker_block", "liquidity_sweep",
    "pdh", "pdl", "pdh_sweep", "pdl_sweep",
    "candle_break",
]
KNOWN_SESSIONS = ["asian", "london", "ny"]
KNOWN_CONDITION_TYPES = ["indicator_compare", "price_compare", "concept", "session", "trend", "raw"]
KNOWN_TIMEFRAME_ROLES = ["bias", "trend", "analysis", "entry", "confirmation"]
KNOWN_SLTP_TYPES = ["fixed_pct", "atr_multiple", "structure", "rr", "level", "unknown"]

_CONDITION_SCHEMA_NOTE = """Each condition object: {"type": one of indicator_compare|price_compare|concept|session|trend|raw, "indicator": indicator name (only for indicator_compare/price_compare), "params": {"period": N} if applicable else {}, "op": ">" or "<" only, "value": number (for indicator_compare), "name": concept/session name (for concept/session types), "direction": "bullish"|"bearish"|null (for concept/trend types), "text": the original phrase (required when type="raw" -- use raw ONLY when you cannot express the rule with the vocabulary below), "role": null (leave null), "lookback_bars": null (leave null)."""


def build_structured_extraction_prompt(source_hint=None, content_type=None):
    """Returns the system prompt instructing the AI to directly produce a
    StrategyConfig/Lesson-shaped JSON structure using only the backtest
    engine's real executable vocabulary.

    content_type (Part 2, explicit type selector): "strategy" | "lesson" |
    "mixed"/None. Previously the AI had to guess purely from the text
    whether a document was a strategy, a lesson, or both -- a real
    contributor to strategies coming back low-confidence/misclassified
    (needing clarification) or lesson content getting forced into a
    half-built "strategy". When the CEO tells us up front, that guess is
    replaced with a direct instruction. "mixed"/None leaves the AI's
    existing free judgment completely unchanged (this is also what an
    unspecified selector defaults to, in sindhu_web/api/ai_integration.py)."""
    hint_note = ""
    if content_type == "strategy":
        hint_note += (
            "The user has told you in advance that this document is a TRADING STRATEGY "
            "(not a general lesson document): focus on extracting complete, executable "
            "entry/exit/confirmation/stop-loss/take-profit/risk rules into the `strategy` "
            "field. Still record any genuine standalone lessons/psychology notes you notice, "
            "but do not leave `strategy` null just because the document also contains "
            "commentary -- look hard for the actual trade rules.\n\n"
        )
    elif content_type == "lesson":
        hint_note += (
            "The user has told you in advance that this document is a LESSON / KNOWLEDGE "
            "document, NOT a trading strategy: you MUST set `strategy` to null, even if the "
            "text mentions trade-like rules or numbers -- put that content into `lessons` "
            "and `psychology_notes` instead. Do not attempt to build an executable strategy "
            "from this document.\n\n"
        )
    if source_hint == "youtube_transcript":
        hint_note += (
            "This text is a raw YouTube video transcript: expect filler words, "
            "false starts, repeated phrases, and missing punctuation -- read "
            "through that noise to the actual trading content.\n\n"
        )
    elif source_hint == "notebooklm":
        hint_note += (
            "This text is a NotebookLM-style research report: it may combine "
            "several sub-topics (strategy, lessons, psychology, risk, "
            "definitions) in one document -- extract and combine all of them.\n\n"
        )
    elif source_hint == "pdf_text":
        hint_note += (
            "This text was extracted from a PDF and may contain page-break "
            "artifacts, broken line wraps, or repeated headers/footers -- read "
            "through that noise to the actual trading content.\n\n"
        )

    indicators_list = ", ".join(KNOWN_INDICATORS)
    sessions_list = ", ".join(KNOWN_SESSIONS)
    categories_list = ", ".join(LESSON_CATEGORIES)

    return (
        "You are a professional institutional trader and quantitative analyst. "
        "You are the ONLY teacher SINDHU (an automated trading knowledge base) "
        "will ever have for this document -- after this one pass, SINDHU must "
        "be able to run this strategy forever without you. Read the ENTIRE "
        "document and understand it deeply: context, meaning, relationships, "
        "hidden logic, trading psychology, institutional concepts, market "
        "structure, risk management, order flow, liquidity, cause and effect. "
        "Never just keyword-match or summarize.\n\n"
        + hint_note +
        "Extract a COMPLETE, directly machine-readable strategy (if the "
        "document describes one) and EVERY lesson, using ONLY this exact "
        "vocabulary so your output can be executed directly by the backtest "
        "engine without any further parsing:\n"
        f"- Indicators/concepts (for \"indicator\" on indicator_compare/price_compare, or \"name\" on concept conditions): {indicators_list}\n"
        f"- Sessions (for \"name\" on session conditions, and session_filter): {sessions_list}\n"
        f"- Timeframe roles: {', '.join(KNOWN_TIMEFRAME_ROLES)}\n"
        f"- Stop-loss/take-profit types: {', '.join(KNOWN_SLTP_TYPES)}\n"
        f"- Lesson categories: {categories_list}\n\n"
        "BE DECISIVE. Ordinary trading language has ordinary meanings -- if a "
        "phrase maps onto the vocabulary above with reasonable confidence, "
        "COMMIT to that mapping and emit a real condition. Do NOT hedge, do "
        "NOT emit type=\"raw\", and do NOT defer to the user just because the "
        "wording isn't identical to the vocabulary term. A raw condition is "
        "NOT a safe middle ground: the backtest engine cannot execute it at "
        "all, so the strategy silently produces zero trades and the user has "
        "to hand-fix it. An imperfect-but-executable mapping is strictly "
        "better than raw. Reserve type=\"raw\" for content that genuinely has "
        "NO equivalent in the vocabulary above (see the RAW test below).\n\n"
        "Common phrasing you MUST map directly rather than flag as unclear:\n"
        "  * \"previous day's high\", \"prior day high\", \"yesterday's high\", "
        "\"PDH\" -> {\"type\": \"concept\", \"name\": \"pdh\"}; the low/PDL "
        "equivalents -> {\"type\": \"concept\", \"name\": \"pdl\"}\n"
        "  * \"green candle\", \"bullish candle\", \"up candle\" = a bullish "
        "candle; \"red candle\", \"bearish candle\", \"down candle\" = a "
        "bearish candle. When the rule is \"wait for a green/red candle, then "
        "enter when its high/low is broken by a later candle\" (a trigger-"
        "candle rule) -> {\"type\": \"concept\", \"name\": \"candle_break\", "
        "\"direction\": \"bullish\"} for green/long, \"bearish\" for red/short. "
        "Add \"candle_break\" to concepts_used.\n"
        "  * \"broken\", \"breaks\", \"breaks above/below\", \"crosses\", "
        "\"takes out\", \"sweeps through\" a named level -> commit to the "
        "concept for that level (pdh/pdl/support/resistance) rather than raw\n"
        "  * \"price moves above/below X\" where X is an indicator -> "
        "{\"type\": \"price_compare\", \"indicator\": X, \"op\": \">\"|\"<\"}\n"
        "  * a stop/target described only in words (\"SL below the recent "
        "swing low\", \"TP at the opposite extreme\") -> a stop_loss/"
        "take_profit TYPE (\"structure\"/\"level\"/\"rr\"), NOT an entry or "
        "exit condition, and NOT raw\n\n"
        "HOW entry_conditions IS EXECUTED (get this wrong and the strategy "
        "is silently meaningless): every condition in entry_conditions is "
        "AND-ed together on the SAME bar, and the trade direction is taken "
        "from the conditions themselves. It is ONE directional setup, not a "
        "menu of alternatives.\n"
        "  * NEVER mix a bullish and a bearish version of the same concept "
        "in entry_conditions (e.g. bullish candle_break AND bearish "
        "candle_break). That is not \"long or short\" -- it demands both at "
        "once, which is either impossible or trivially always-true, and "
        "produces a strategy that is nonsense either way.\n"
        "  * If the document describes BOTH a long setup and a mirror-image "
        "short setup, extract ONLY the long setup into entry_conditions "
        "(the short side is the same logic mirrored, and the engine cannot "
        "hold two setups). Do not average them together or drop their "
        "filters to make them fit.\n"
        "  * Keep EVERY filter that gates the entry. If the rule is \"price "
        "sweeps below PDL, THEN a green candle forms, THEN its high "
        "breaks\", all of those belong in entry_conditions together (pdl + "
        "candle_break) -- dropping the pdl filter turns a selective setup "
        "into one that fires on almost every bar. A condition list that is "
        "true on most bars means you dropped the filters.\n\n"
        "TWO HARD CONSISTENCY RULES (violating either makes the strategy "
        "unrunnable):\n"
        "  1. exit_conditions is ONLY for rules that close a trade on a "
        "market EVENT (e.g. an opposite BOS). A stop-loss or take-profit "
        "belongs in the stop_loss/take_profit fields and NOWHERE else -- "
        "never also add it to exit_conditions, and never emit an "
        "exit_condition whose text is just a type name like \"structure\" "
        "or \"rr\". If the document's only exits are the SL and TP, then "
        "exit_conditions MUST be [].\n"
        "  2. stop_loss/take_profit type \"structure\" means \"anchored to a "
        "structural zone\", so concepts_used MUST also contain the concept "
        "that zone comes from (support, resistance, fvg, order_block, "
        "breaker_block, or liquidity_sweep). If the stop is really anchored "
        "to the previous day's level, use type \"level\" with \"level\": "
        "\"pdh\"|\"pdl\" instead. If it is a fixed distance, use "
        "\"fixed_pct\"/\"atr_multiple\" with a value.\n\n"
        "THE RAW TEST -- only use type=\"raw\" if BOTH are true: (1) the rule "
        "names a specific indicator, pattern, or mechanism with no equivalent "
        "in the vocabulary above (e.g. a proprietary indicator, a trendline "
        "drawing rule, a chart pattern like head-and-shoulders), AND (2) no "
        "reasonable trader reading it would agree on which vocabulary term it "
        "means. If a competent trader would confidently say \"that's just X\", "
        "then it IS X -- emit X.\n\n"
        "COMPLETE every rule you can confidently infer from context even if "
        "the source never states it explicitly. Other concrete mappings you "
        "should apply directly:\n"
        "  * 'buy/enter from demand', 'demand zone', 'demand area' -> "
        "{\"type\": \"concept\", \"name\": \"support\", \"direction\": \"bullish\"}\n"
        "  * 'sell/enter from supply', 'supply zone', 'supply area' -> "
        "{\"type\": \"concept\", \"name\": \"resistance\", \"direction\": \"bearish\"}\n"
        "  * 'wait for confirmation' / 'confirmation trigger' with no more "
        "specific description -> {\"type\": \"concept\", \"name\": \"bos\", "
        "\"direction\": \"bullish\"|\"bearish\"} (use \"choch\" instead if the "
        "context is about a trend reversal rather than a continuation)\n"
        "  * 'liquidity sweep', 'stop hunt', 'liquidity grab' -> "
        "{\"type\": \"concept\", \"name\": \"liquidity_sweep\"}\n"
        "  * a missing take-profit is often a swing high/liquidity "
        "pool/previous-high (use stop_loss/take_profit type \"structure\" "
        "or \"level\") or a dynamic RR (type \"rr\", pick a reasonable "
        "value like 2.0 if the strategy's own risk discussion implies one); "
        "a missing stop-loss is often a swing low/structure low (type "
        "\"structure\") or ATR-based (type \"atr_multiple\") depending on "
        "the strategy -- only fall back to type \"unknown\" if truly "
        "nothing in the text or its trading logic suggests a placement.\n"
        "Never invent a number or fact with no basis in the source text or "
        "in ordinary trading logic -- but ordinary, well-known trading logic "
        "(e.g. stops go beyond structure, targets sit at the next liquidity "
        "level) IS a valid basis, not a guess.\n\n"
        f"{_CONDITION_SCHEMA_NOTE}\n\n"
        "Respond with ONLY a single JSON object (no markdown fences, no "
        "commentary before or after) with exactly these keys:\n"
        "{\n"
        '  "confidence": 0-100 -- how confident you are that the extracted rules are COMPLETE and CORRECT,\n'
        '      i.e. that running them would reproduce what the author actually described. Judge the SUBSTANCE,\n'
        '      not the wording: confidently mapping familiar phrasing ("previous day high" -> pdh) should NOT\n'
        '      lower this. Score BELOW 60 only when something material is genuinely unresolved -- a rule you\n'
        '      had to leave raw, a self-contradictory instruction, or a missing piece that changes what the\n'
        '      strategy does. Below 60 sends this to the user for manual clarification, so do not go there for\n'
        '      wording you understood.\n'
        '  "strategy": null OR {\n'
        '    "name": "",\n'
        '    "timeframes": {"entry": "1h"},\n'
        '    "indicators": [{"name": "ema", "params": {"period": 50}, "role": "trend"}],\n'
        '    "concepts_used": ["bos"],\n'
        '    "entry_conditions": [<condition>],\n'
        '    "exit_conditions": [<condition>],\n'
        '    "confirmation_conditions": [<condition>],\n'
        '    "stop_loss": {"type": "structure", "value": null, "level": null},\n'
        '    "take_profit": {"type": "rr", "value": 2.0, "level": null},\n'
        '    "risk_pct": 1.0,\n'
        '    "risk_reward": 2.0,\n'
        '    "session_filter": [],\n'
        '    "trend_filter": null\n'
        "  },\n"
        '  "lessons": [{"title": "", "category": "", "description": "", "tags": [], "rule_type": "block_if_true", "direction": null, "condition": null}],\n'
        '  "dictionary_terms": [{"term": "", "definition": "", "category": "structure|indicator|session|trend|risk|psychology|pattern", "aliases": [], "examples": [], "related_concepts": [], "usage": ""}],\n'
        '  "inferred_fields": [{"field": "", "confidence": 0.0, "reason": "", "evidence": ""}],\n'
        '      -- REQUIRED: add one entry here for EVERY phrase you mapped onto a vocabulary term whose wording\n'
        '         differed from the term itself, so the user can audit your reading without re-reading the source.\n'
        '         Put the original phrase in "evidence" and the mapping in "reason",\n'
        '         e.g. {"field": "entry_conditions[0]", "confidence": 0.95,\n'
        '               "reason": "mapped to concept pdl (previous day low)",\n'
        '               "evidence": "Price must cross below the Previous Day\'s Low"}.\n'
        '  "missing_rules": [""],\n'
        '  "psychology_notes": [""]\n'
        "}\n\n"
        "Set \"strategy\" to null ONLY if the document has no executable "
        "trading strategy at all (pure lesson/psychology/risk-notes/"
        "market-structure content). Every list may be empty ([]) if nothing "
        "applies -- never fabricate an entry just to fill a list."
    )


_REQUIRED_KEYS = {
    "confidence": 0,
    "strategy": None,
    "lessons": [],
    "dictionary_terms": [],
    "inferred_fields": [],
    "missing_rules": [],
    "psychology_notes": [],
}

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def _extract_json_object(text):
    """Best-effort: strip code fences, then take the substring from the
    first '{' to the last '}' (models occasionally add a stray sentence
    before/after the JSON despite instructions)."""
    cleaned = _CODE_FENCE_RE.sub("", text or "").strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return cleaned[start:end + 1]


def _escape_literal_control_chars_in_strings(raw):
    """Models very often emit a real newline/tab inside a multi-line JSON
    string value instead of the escaped \\n json.loads requires --
    technically invalid JSON that every mainstream provider still produces
    routinely for long text fields. Rather than reject it, walk the text
    once tracking whether we're inside a string literal (respecting escape
    sequences) and escape any literal control character found there. Never
    touches structural whitespace outside of strings."""
    out = []
    in_string = False
    escaped = False
    for ch in raw:
        if in_string:
            if escaped:
                out.append(ch)
                escaped = False
            elif ch == "\\":
                out.append(ch)
                escaped = True
            elif ch == '"':
                out.append(ch)
                in_string = False
            elif ch == "\n":
                out.append("\\n")
            elif ch == "\r":
                out.append("\\r")
            elif ch == "\t":
                out.append("\\t")
            else:
                out.append(ch)
        else:
            out.append(ch)
            if ch == '"':
                in_string = True
    return "".join(out)


def _parse_json_object(raw_text):
    """Never raises. Returns a parsed dict, or None if no repairable JSON
    object was found."""
    candidate = _extract_json_object(raw_text)
    if not candidate:
        return None
    try:
        return json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        try:
            return json.loads(_escape_literal_control_chars_in_strings(candidate))
        except (json.JSONDecodeError, ValueError):
            return None


def _clean_str_list(value):
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _clean_condition(entry):
    """Returns a plain dict (not yet a Condition dataclass -- vocabulary
    validation against the executable indicator/concept/session set happens
    in strategy_builder.py, which is what actually constructs the dataclass
    and decides what must be demoted to type='raw')."""
    if not isinstance(entry, dict):
        return None
    cond_type = str(entry.get("type") or "raw").strip().lower()
    if cond_type not in KNOWN_CONDITION_TYPES:
        cond_type = "raw"
    op = entry.get("op")
    if op not in (">", "<", None):
        op = None
    try:
        value = float(entry["value"]) if entry.get("value") is not None else None
    except (TypeError, ValueError):
        value = None
    try:
        lookback = int(entry["lookback_bars"]) if entry.get("lookback_bars") is not None else None
    except (TypeError, ValueError):
        lookback = None
    params = entry.get("params") if isinstance(entry.get("params"), dict) else {}
    direction = entry.get("direction")
    if direction not in ("bullish", "bearish", None):
        direction = None
    return {
        "type": cond_type,
        "indicator": (str(entry.get("indicator")).strip().lower() if entry.get("indicator") else None),
        "params": params,
        "op": op,
        "value": value,
        "name": (str(entry.get("name")).strip().lower() if entry.get("name") else None),
        "direction": direction,
        "text": (str(entry.get("text")).strip() if entry.get("text") else None),
        "role": None,
        "lookback_bars": lookback,
    }


def _clean_sltp(entry):
    if not isinstance(entry, dict):
        return {"type": "unknown", "value": None, "level": None}
    sltp_type = str(entry.get("type") or "unknown").strip().lower()
    if sltp_type not in KNOWN_SLTP_TYPES:
        sltp_type = "unknown"
    try:
        value = float(entry["value"]) if entry.get("value") is not None else None
    except (TypeError, ValueError):
        value = None
    level = entry.get("level")
    if level not in ("pdh", "pdl", None):
        level = None
    return {"type": sltp_type, "value": value, "level": level}


def _clean_strategy(entry):
    if not isinstance(entry, dict):
        return None
    timeframes = entry.get("timeframes") if isinstance(entry.get("timeframes"), dict) else {}
    timeframes = {
        role: str(tf).strip().lower() for role, tf in timeframes.items()
        if role in KNOWN_TIMEFRAME_ROLES and tf
    }
    indicators = []
    for ind in (entry.get("indicators") or []):
        if isinstance(ind, dict) and ind.get("name"):
            indicators.append({
                "name": str(ind["name"]).strip().lower(),
                "params": ind.get("params") if isinstance(ind.get("params"), dict) else {},
                "role": str(ind.get("role")).strip().lower() if ind.get("role") else None,
            })

    def _conditions(key):
        raw = entry.get(key)
        if not isinstance(raw, list):
            return []
        return [c for c in (_clean_condition(e) for e in raw) if c]

    try:
        risk_pct = float(entry["risk_pct"]) if entry.get("risk_pct") is not None else None
    except (TypeError, ValueError):
        risk_pct = None
    try:
        risk_reward = float(entry["risk_reward"]) if entry.get("risk_reward") is not None else None
    except (TypeError, ValueError):
        risk_reward = None

    trend_filter = entry.get("trend_filter")
    if trend_filter not in ("up", "down", None):
        trend_filter = None

    return {
        "name": str(entry.get("name") or "").strip(),
        "timeframes": timeframes,
        "indicators": indicators,
        "concepts_used": _clean_str_list(entry.get("concepts_used")),
        "entry_conditions": _conditions("entry_conditions"),
        "exit_conditions": _conditions("exit_conditions"),
        "confirmation_conditions": _conditions("confirmation_conditions"),
        "stop_loss": _clean_sltp(entry.get("stop_loss")),
        "take_profit": _clean_sltp(entry.get("take_profit")),
        "risk_pct": risk_pct,
        "risk_reward": risk_reward,
        "session_filter": [s for s in _clean_str_list(entry.get("session_filter")) if s in KNOWN_SESSIONS],
        "trend_filter": trend_filter,
    }


def _clean_lesson(entry):
    if not isinstance(entry, dict):
        return None
    title = str(entry.get("title") or "").strip()
    description = str(entry.get("description") or "").strip()
    if not title or not description:
        return None
    category = str(entry.get("category") or "Other").strip()
    if category not in LESSON_CATEGORIES:
        category = "Other"
    rule_type = entry.get("rule_type")
    if rule_type not in ("block_if_true", "require_if_true"):
        rule_type = "block_if_true"
    direction = entry.get("direction")
    if direction not in ("bullish", "bearish", None):
        direction = None
    return {
        "title": title,
        "category": category,
        "description": description,
        "tags": _clean_str_list(entry.get("tags")),
        "rule_type": rule_type,
        "direction": direction,
        "condition": _clean_condition(entry.get("condition")) if entry.get("condition") else None,
    }


def _clean_dictionary_term(entry):
    if not isinstance(entry, dict):
        return None
    term = str(entry.get("term") or "").strip()
    definition = str(entry.get("definition") or "").strip()
    if not term or not definition:
        return None
    return {
        "term": term,
        "definition": definition,
        "category": str(entry.get("category") or "structure").strip().lower() or "structure",
        "aliases": _clean_str_list(entry.get("aliases")),
        "examples": _clean_str_list(entry.get("examples")),
        "related_concepts": _clean_str_list(entry.get("related_concepts")),
        "usage": str(entry.get("usage") or "").strip(),
    }


def _clean_inferred_field(entry):
    if not isinstance(entry, dict):
        return None
    field = str(entry.get("field") or "").strip()
    if not field:
        return None
    try:
        confidence = float(entry.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))
    return {
        "field": field,
        "confidence": round(confidence, 2),
        "reason": str(entry.get("reason") or "").strip(),
        "evidence": str(entry.get("evidence") or "").strip(),
    }


def parse_structured_response(raw_text):
    """Never raises. Returns a fully-populated, vocabulary-sanitized dict
    matching _REQUIRED_KEYS, or None if the response contained no parseable
    JSON object at all -- callers treat None exactly like "this provider
    failed", moving to the next one in the fallback chain / Offline Mode."""
    data = _parse_json_object(raw_text)
    if not isinstance(data, dict):
        return None

    result = dict(_REQUIRED_KEYS)
    try:
        result["confidence"] = max(0, min(100, float(data.get("confidence", 0))))
    except (TypeError, ValueError):
        result["confidence"] = 0

    result["strategy"] = _clean_strategy(data.get("strategy"))

    lessons = data.get("lessons")
    if isinstance(lessons, list):
        result["lessons"] = [l for l in (_clean_lesson(e) for e in lessons) if l]

    dictionary_terms = data.get("dictionary_terms")
    if isinstance(dictionary_terms, list):
        result["dictionary_terms"] = [t for t in (_clean_dictionary_term(e) for e in dictionary_terms) if t]

    inferred_fields = data.get("inferred_fields")
    if isinstance(inferred_fields, list):
        # A reported "inference" with ~zero confidence is really the model
        # saying "I could not infer this" -- that belongs in missing_rules,
        # not as a noisy zero-confidence row in the Inferred Fields display.
        result["inferred_fields"] = [
            f for f in (_clean_inferred_field(e) for e in inferred_fields) if f and f["confidence"] > 0.05
        ]

    for key in ("missing_rules", "psychology_notes"):
        value = data.get(key)
        if isinstance(value, list):
            result[key] = [str(v).strip() for v in value if str(v).strip()]

    return result
