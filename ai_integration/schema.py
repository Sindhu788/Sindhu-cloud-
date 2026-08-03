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
    # Volume-based
    "poc", "value_area", "lvn", "hvn", "aggression",
    # Structure-based (beyond BOS/CHoCH/FVG/order_block/breaker_block above)
    "mitigation_block", "imbalance", "equal_highs_lows", "swing_high", "swing_low",
    # Session-based (beyond the session_filter session names below)
    "session_high_low", "session_open",
    # Price-action
    "engulfing", "pin_bar", "inside_bar",
    # Advanced Concept Library expansion (Genuine Evolution Engine + Advanced
    # Concept Library batch): rejection_block/premium_discount_zone/orb/
    # initial_balance are type="concept"; anchored_vwap/cvd are period-less
    # indicators (usable via price_compare/indicator_compare, same as vwap).
    "premium_discount_zone", "rejection_block", "orb", "initial_balance",
    "anchored_vwap", "cvd", "kill_zone",
]
KNOWN_SESSIONS = ["asian", "london", "ny"]
KNOWN_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
KNOWN_CONDITION_TYPES = ["indicator_compare", "price_compare", "indicator_vs_indicator", "concept", "session", "trend", "raw", "candle_range_pct"]
KNOWN_TIMEFRAME_ROLES = ["bias", "trend", "analysis", "entry", "confirmation"]
KNOWN_SLTP_TYPES = ["fixed_pct", "atr_multiple", "structure", "rr", "level", "signal_candle", "unknown"]
KNOWN_ENTRY_TYPES = ["market", "current_candle_close", "next_candle_open", "limit", "stop", "signal_candle_high", "signal_candle_low"]

_CONDITION_SCHEMA_NOTE = """Each condition object: {"type": one of indicator_compare|price_compare|indicator_vs_indicator|concept|session|trend|candle_range_pct|raw, "indicator": indicator name (for indicator_compare/price_compare/indicator_vs_indicator -- for indicator_vs_indicator this is the FIRST indicator), "params": {"period": N} if applicable else {} (for indicator_vs_indicator, this is the first indicator's params; for candle_range_pct, {"min_pct": N, "max_pct": N} -- either may be omitted to leave that side unbounded), "op": ">" or "<" only, "value": number (REQUIRED for indicator_compare -- compares the indicator to this fixed number; leave null/omit for price_compare and indicator_vs_indicator, which never use it), "indicator2": ONLY for type="indicator_vs_indicator" -- the SECOND indicator's name, "params2": ONLY for type="indicator_vs_indicator" -- the second indicator's params (e.g. {"period": 50}), "name": concept/session name (for concept/session types), "direction": "bullish"|"bearish"|null (for concept/trend types), "text": the original phrase (required when type="raw" -- use raw ONLY when you cannot express the rule with the vocabulary below), "role": for "concept" AND "indicator_vs_indicator" conditions, the timeframe role (one of the declared Timeframe roles below, e.g. "bias"/"trend"/"analysis") that THIS SPECIFIC comparison is actually read from -- for indicator_vs_indicator BOTH indicators come from this SAME role (e.g. "Trend (1H): 20 EMA above 50 EMA" -> role="trend", both EMAs are the 1H versions); set it whenever the text names a timeframe for it (e.g. "a swing low on the 1H or 4H chart" -> role of whichever declared role is 1h or 4h); leave null when the text doesn't say (this defaults to the entry timeframe, which is correct for most entry/confirmation-timeframe rules like a 1-minute candle_break trigger) -- never leave every condition on the entry timeframe just because that's simpler than reading which chart the text actually says it's on, "lookback_bars": null (leave null).

USE type="candle_range_pct" whenever the document puts a percentage-range requirement on a candle's OWN size/range (e.g. "the signal candle's range must be between 0.15% and 3.0%") -- this is a real, executable filter, not a raw/unparseable rule."""


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
        "  Each role's value must be ONE concrete interval (\"5m\", \"1h\", \"1d\", ...) -- never a "
        "slash/or-separated list like \"5m/15m\" or \"5-minute or 15-minute\", even if the source text "
        "itself offers alternatives. If the text gives a choice, pick whichever one it actually uses in "
        "its own worked example, or the smaller/more granular option if no example disambiguates it.\n"
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
        "exit condition, and NOT raw\n"
        "  * \"Volume Profile\", \"Point of Control\", \"POC\" -> concept "
        "\"poc\"; \"Value Area\", \"VAH\"/\"VAL\" -> concept \"value_area\"; "
        "\"Low Volume Node\"/\"LVN\" -> \"lvn\"; \"High Volume Node\"/\"HVN\" "
        "-> \"hvn\"\n"
        "  * a strong/aggressive candle with a volume spike, described as "
        "\"aggressive buying/selling\", \"institutional aggression\", or "
        "\"high-conviction move\" -> concept \"aggression\" (with direction)\n"
        "  * \"Mitigation Block\" -> \"mitigation_block\"; a single candle "
        "described as an \"inefficiency\" or \"imbalance\" WITHOUT the "
        "3-candle-gap framing of an FVG -> \"imbalance\"; \"Equal Highs\"/"
        "\"Equal Lows\"/\"EQH\"/\"EQL\" -> \"equal_highs_lows\"; an explicit "
        "\"swing high\"/\"swing low\" EVENT (not the support/resistance zone "
        "itself) -> \"swing_high\"/\"swing_low\"\n"
        "  * \"session high/low\", \"Asian/London/NY high or low\" (the "
        "developing session's own extreme, not yesterday's PDH/PDL) -> "
        "concept \"session_high_low\"; \"session open\", \"London open\", "
        "\"NY open price\" -> concept \"session_open\"\n"
        "  * a day-of-week rule (\"only trade Mondays\", \"avoid Fridays\") -> "
        "populate the top-level \"day_filter\" list (lowercase day names), "
        "NOT a condition\n"
        "  * \"engulfing candle\" -> \"engulfing\"; \"pin bar\", \"rejection "
        "candle\", \"hammer\", \"shooting star\" -> \"pin_bar\"; \"inside "
        "bar\" -> \"inside_bar\"\n"
        "  * \"move stop to breakeven\", \"stop to entry once in profit\" -> "
        "populate the top-level \"breakeven_at_rr\" number (how many "
        "multiples of the original risk must be reached first), NOT a "
        "condition\n"
        "  * an inline EXCLUSION/NEGATION clause that is part of the entry "
        "criteria (\"do NOT enter if RSI above 70\", \"do not take the trade "
        "if the SL distance is less than 0.15% or greater than 1.5%\", "
        "\"avoid the setup unless the RR is at least 2\") must never be "
        "silently dropped or folded into the wrong lesson/filter. If it's a "
        "simple indicator/price comparison, INVERT the operator and add it "
        "directly to the same entry-condition AND-gate (\"don't enter if RSI "
        "> 70\" becomes an ordinary \"RSI < 70\" condition in the list). If "
        "it's a numeric range/ratio filter that has no direct inverted-"
        "comparison equivalent (e.g. a SL-distance-% range, an RR-ratio "
        "floor), do NOT invent a fake condition type for it and do NOT "
        "attach it to an unrelated lesson -- instead emit it as its own "
        "entry in \"lessons\" with \"rule_type\": \"block_if_true\", a "
        "\"condition\" describing the excluded case in the SAME schema as "
        "any other condition, and a \"title\"/\"description\" that states "
        "the exact numeric filter from the source text so it stays "
        "traceable back to it.\n\n"
        "HOW entry_conditions/long_entry_conditions/short_entry_conditions "
        "ARE EXECUTED (get this wrong and the strategy is silently "
        "meaningless): every condition within ONE of these lists is AND-ed "
        "together on the SAME bar. entry_conditions is ONE directional "
        "setup (direction is taken from the conditions themselves), not a "
        "menu of alternatives.\n"
        "  * If the document describes ONLY ONE direction (a long-only or "
        "short-only strategy), use entry_conditions exactly as before -- "
        "leave long_entry_conditions/short_entry_conditions empty ([]).\n"
        "  * If the document describes BOTH a long setup and a mirror-image "
        "short setup (the common case: \"Long Entry Rules\" / \"Short Entry "
        "Rules\" sections, or \"Long (mirror of short)\"), put the long "
        "rules in long_entry_conditions and the short rules in "
        "short_entry_conditions -- these are TWO SEPARATE, independently "
        "AND-ed rule sets, evaluated independently, NOT merged into one "
        "list. Leave entry_conditions empty ([]) in this case. Do not "
        "average the two setups together or drop either one's filters to "
        "make them fit into a single list -- that used to be necessary and "
        "isn't anymore.\n"
        "  * NEVER mix a bullish and a bearish version of the same concept "
        "within the SAME list (e.g. bullish candle_break AND bearish "
        "candle_break both inside entry_conditions, or both inside "
        "long_entry_conditions). That is not \"long or short\" -- it "
        "demands both at once within one AND-gate, which is either "
        "impossible or trivially always-true. The bearish version belongs "
        "in short_entry_conditions instead, not alongside the bullish one.\n"
        "  * Keep EVERY filter that gates the entry, in whichever list it "
        "belongs to. If the rule is \"price sweeps below PDL, THEN a green "
        "candle forms, THEN its high breaks\", all of those belong together "
        "in the same list (pdl + candle_break) -- dropping the pdl filter "
        "turns a selective setup into one that fires on almost every bar. A "
        "condition list that is true on most bars means you dropped the "
        "filters.\n\n"
        "BRANCHING / CONDITIONAL ENTRY LOGIC (\"if the market shows shape/"
        "regime X, enter this way; if Y, enter that way\" -- e.g. a "
        "strategy with THREE OR MORE distinct alternative setups for the "
        "same direction, or entry rules that explicitly depend on which "
        "named state/pattern/shape is currently active): entry_conditions/"
        "long_entry_conditions/short_entry_conditions can each only "
        "represent ONE AND-gated setup per direction -- do NOT try to "
        "merge multiple alternative setups into one of these lists by "
        "picking a subset of conditions or averaging them together, and do "
        "NOT invent a fake extra AND-condition to fake-select between "
        "them. Instead use the top-level \"entry_rule_groups\" list: each "
        "item is {\"label\": a short name for THIS specific setup (e.g. "
        "\"P-Shape Continuation\", \"B-Shape Breakout\"), \"direction\": "
        "\"bullish\"|\"bearish\", \"conditions\": [<condition>, ...]} -- "
        "conditions within ONE group are AND-ed together exactly like "
        "entry_conditions; groups are OR'd against each other (ANY group "
        "whose conditions are all true fires an entry in that group's "
        "direction). Use entry_rule_groups INSTEAD OF entry_conditions/"
        "long_entry_conditions/short_entry_conditions when the document "
        "genuinely has this branching shape -- leave those three empty "
        "([]) in that case. A simple long-setup/short-setup pair (exactly "
        "one setup per direction) still belongs in long_entry_conditions/"
        "short_entry_conditions as before -- entry_rule_groups is for "
        "when there are MULTIPLE alternative setups, not just two mirrored "
        "ones.\n\n"
        "INDICATOR-VS-INDICATOR COMPARISONS (MA cross, MA alignment, EMA "
        "vs EMA): indicator_compare only compares an indicator to a FIXED "
        "NUMBER (e.g. \"RSI > 40\") and price_compare only compares price "
        "to an indicator -- neither can express one indicator compared to "
        "ANOTHER indicator. For that, use type=\"indicator_vs_indicator\": "
        "\"20-period EMA above 50-period EMA\" -> {\"type\": "
        "\"indicator_vs_indicator\", \"indicator\": \"ema\", \"params\": "
        "{\"period\": 20}, \"op\": \">\", \"indicator2\": \"ema\", "
        "\"params2\": {\"period\": 50}}. Also declare BOTH periods in the "
        "top-level \"indicators\" list (two separate entries, same role, "
        "different \"period\") so they actually get computed -- an "
        "indicator_vs_indicator condition whose indicators aren't also "
        "listed there will never produce a value. Do NOT emit this as "
        "type=\"raw\" just because it's two indicators instead of one -- "
        "this is exactly the vocabulary for it.\n\n"
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
        "\"fixed_pct\"/\"atr_multiple\" with a value. If the stop is "
        "anchored to the SIGNAL CANDLE ITSELF (the specific trigger candle "
        "the entry rule refers to, e.g. \"stop-loss = the signal candle's "
        "high * 1.003\"), use stop_loss type \"signal_candle\" with "
        "\"value\" = the buffer written as an ORDINARY PERCENT NUMBER, the "
        "exact same convention fixed_pct already uses elsewhere (1.0 means "
        "1%, NOT 0.01) -- IMPORTANT: a multiplier like \"*1.003\" in the "
        "source text is a 0.3% buffer, so \"value\" must be 0.3, never the "
        "raw decimal 0.003 from the multiplier -- do not use \"structure\" "
        "for this, structure means a swing/OB/FVG zone, not the specific "
        "candle the entry itself fired on.\n\n"
        "ENTRY EXECUTION TYPE (top-level \"entry_type\" field, default "
        "\"market\") -- set this whenever the document describes HOW an "
        "entry actually fills, not just the condition that identifies it:\n"
        "  * \"signal_candle_high\" / \"signal_candle_low\": the rule is "
        "\"wait for a LATER candle to break above/below THIS SPECIFIC "
        "candle's high/low\" (e.g. \"enter when a later candle's low goes "
        "below the signal candle's low\") -- use \"signal_candle_low\" for "
        "that example (a short/bearish break), \"signal_candle_high\" for "
        "the bullish/long equivalent. This is DIFFERENT from a plain "
        "candle_break concept condition: entry_type actually fills the "
        "trade at that exact broken price, one time, off the ONE specific "
        "candle the entry condition matched -- always set this whenever "
        "the text's entry mechanism is phrased as \"wait for a later "
        "candle to break this one\", not just \"a candle_break happened\".\n"
        "  * \"next_candle_open\": enter at the open of the bar immediately "
        "after the signal.\n"
        "  * \"limit\" / \"stop\": enter at a specific offset from the "
        "signal price (set \"entry_price_offset_pct\" too) -- \"limit\" for "
        "a pullback entry, \"stop\" for a breakout entry.\n"
        "  * Leave as \"market\" (or omit) for \"enter immediately when the "
        "condition is true\", the ordinary case.\n\n"
        "PRE-TRADE DISCARD FILTERS (top-level fields, all optional, all "
        "None/omitted = no filtering) -- these THROW AWAY a signal that "
        "would otherwise fire, rather than shaping the trade that happens. "
        "Only set these when the document states an explicit numeric "
        "skip/discard rule, never invent one:\n"
        "  * \"sl_distance_filter_pct\": {\"min_pct\": N, \"max_pct\": N} -- "
        "\"if the stop-loss distance is less than X% or more than Y% of "
        "entry price, do not take the trade\".\n"
        "  * \"min_risk_reward_filter\": N, together with "
        "\"primary_target_lookback_bars\": N -- \"if the ratio of "
        "(distance to a reference target) / (distance to stop-loss) is "
        "less than N, do not take the trade\", where the reference target "
        "is described as \"the highest high / lowest low of the preceding "
        "N candles\". primary_target_lookback_bars is that N (how many "
        "candles back); min_risk_reward_filter is the minimum required "
        "ratio.\n"
        "  * A condition entry with type \"candle_range_pct\" (see the "
        "condition vocabulary note below) for a percentage-range "
        "requirement on a candle's own size -- this is a condition, not a "
        "top-level field.\n\n"
        "PARTIAL TAKE-PROFIT (top-level \"partial_take_profit\" field, "
        "{\"trigger_rr\": N, \"close_fraction\": F} or null) -- \"close X% "
        "of the position once profit reaches N times the original risk, "
        "let the rest ride to the full take_profit\". close_fraction is "
        "the fraction closed (e.g. 0.8 for \"close 80%\"). If the document "
        "describes a partial exit at a specific STRUCTURAL level (e.g. "
        "\"close 80% at the primary target\") rather than a fixed R "
        "multiple, use the min_risk_reward_filter threshold above (or the "
        "strategy's overall stated minimum RR) as trigger_rr -- that is "
        "the R-multiple that level corresponds to for a trade that passed "
        "the RR filter.\n\n"
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
        "SELF-VERIFICATION -- DO THIS BEFORE YOU ANSWER (mandatory, and it "
        "costs you nothing but a moment's re-reading; the person receiving "
        "this output cannot check your trading logic themselves, so you are "
        "the only line of defence):\n"
        "Re-read the source text and re-read your own draft answer, then "
        "confirm ALL FIVE of the following. If any check fails, FIX IT IN "
        "THIS SAME RESPONSE -- do not hand back an answer you already know "
        "is broken, and do not just mention the problem in missing_rules and "
        "leave it there.\n"
        "  1. COMPLETENESS -- every entry rule and every exit rule the text "
        "describes appears somewhere in your output. Walk the source "
        "top-to-bottom and tick each rule off against your JSON. If the text "
        "describes several ALTERNATIVE ways to enter (per market shape, "
        "regime, or scenario), each one is its own entry_rule_groups entry -- "
        "an alternative you had nowhere to put is still a rule you dropped.\n"
        "  2. NO DUPLICATED ENTRY/EXIT CLAUSE -- no condition in "
        "exit_conditions is the same condition as one in your entry rules. "
        "That would close every trade one bar after it opens. If the text "
        "gives no distinct exit rule, leave exit_conditions empty ([]) and "
        "let stop_loss/take_profit do the work -- an empty exit list is "
        "CORRECT and is always better than a copied one.\n"
        "  3. EXITS CAN ACTUALLY BE REACHED -- exit_conditions is not built "
        "only from slow-moving price levels (support, resistance, pdh, pdl, "
        "poc, value_area, session_high_low). Those stay true for many bars "
        "at a time, so the trade would close immediately instead of running "
        "to its target. Again: prefer an empty exit_conditions plus a real "
        "stop_loss/take_profit.\n"
        "  4. NO IMPOSSIBLE AND-GATE -- within any ONE condition list, no "
        "two conditions contradict each other (an indicator required both "
        "below X and above Y; price required both above a level and below a "
        "lower one; the same concept required both bullish and bearish). "
        "Those can never be true on the same bar, so the strategy would "
        "never trade at all. Long and short rules belong in SEPARATE lists "
        "(long_entry_conditions/short_entry_conditions, or separate "
        "entry_rule_groups entries with opposite \"direction\").\n"
        "  5. RISK IS SET -- stop_loss, take_profit and risk_pct are each "
        "either read from the text or derived from ordinary trading logic as "
        "described above, and only left \"unknown\"/null when the text truly "
        "gives nothing to work from.\n"
        "Silently passing these checks is expected and needs no comment. "
        "Only list something under missing_rules if it genuinely cannot be "
        "resolved from the text at all.\n\n"
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
        '    "long_entry_conditions": [<condition>],\n'
        '    "short_entry_conditions": [<condition>],\n'
        '    "entry_rule_groups": [{"label": "P-Shape Continuation", "direction": "bullish", "conditions": [<condition>]}],\n'
        '    "exit_conditions": [<condition>],\n'
        '    "confirmation_conditions": [<condition>],\n'
        '    "stop_loss": {"type": "structure", "value": null, "level": null},\n'
        '    "take_profit": {"type": "rr", "value": 2.0, "level": null},\n'
        '    "risk_pct": 1.0,\n'
        '    "risk_reward": 2.0,\n'
        '    "session_filter": [],\n'
        '    "trend_filter": null,\n'
        '    "day_filter": [],\n'
        '    "breakeven_at_rr": null,\n'
        '    "entry_type": "market",\n'
        '    "entry_price_offset_pct": null,\n'
        '    "sl_distance_filter_pct": null,\n'
        '    "min_risk_reward_filter": null,\n'
        '    "primary_target_lookback_bars": null,\n'
        '    "partial_take_profit": null\n'
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
    # Only meaningful for type="concept" (see _CONDITION_SCHEMA_NOTE) and
    # only trusted when it's one of the strategy's own declared timeframe
    # roles -- was previously hardcoded to None unconditionally here, which
    # silently discarded the AI's own timeframe understanding even when it
    # correctly said "this swing low is on the 4H chart", forcing every
    # structural concept onto the entry timeframe regardless of what the
    # source document actually described.
    role = str(entry.get("role")).strip().lower() if entry.get("role") else None
    if role not in KNOWN_TIMEFRAME_ROLES:
        role = None
    if cond_type not in ("concept", "indicator_vs_indicator"):
        role = None
    params2 = entry.get("params2") if isinstance(entry.get("params2"), dict) else {}
    return {
        "type": cond_type,
        "indicator": (str(entry.get("indicator")).strip().lower() if entry.get("indicator") else None),
        "params": params,
        "op": op,
        "value": value,
        "name": (str(entry.get("name")).strip().lower() if entry.get("name") else None),
        "direction": direction,
        "text": (str(entry.get("text")).strip() if entry.get("text") else None),
        "role": role,
        "lookback_bars": lookback,
        "indicator2": (str(entry.get("indicator2")).strip().lower() if entry.get("indicator2") else None),
        "params2": params2,
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

    def _rule_groups():
        raw = entry.get("entry_rule_groups")
        if not isinstance(raw, list):
            return []
        groups = []
        for g in raw:
            if not isinstance(g, dict):
                continue
            direction = g.get("direction")
            if direction not in ("bullish", "bearish"):
                continue
            conditions = g.get("conditions")
            conditions = [c for c in (_clean_condition(e) for e in conditions or []) if c] if isinstance(conditions, list) else []
            if not conditions:
                continue
            groups.append({
                "label": str(g.get("label") or "").strip(),
                "direction": direction,
                "conditions": conditions,
            })
        return groups

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

    try:
        breakeven_at_rr = float(entry["breakeven_at_rr"]) if entry.get("breakeven_at_rr") is not None else None
        if breakeven_at_rr is not None and breakeven_at_rr <= 0:
            breakeven_at_rr = None
    except (TypeError, ValueError):
        breakeven_at_rr = None

    entry_type = str(entry.get("entry_type") or "market").strip().lower()
    if entry_type not in KNOWN_ENTRY_TYPES:
        entry_type = "market"
    try:
        entry_price_offset_pct = float(entry["entry_price_offset_pct"]) if entry.get("entry_price_offset_pct") is not None else None
    except (TypeError, ValueError):
        entry_price_offset_pct = None

    def _pct_range_filter(key):
        raw = entry.get(key)
        if not isinstance(raw, dict):
            return None
        try:
            min_pct = float(raw["min_pct"]) if raw.get("min_pct") is not None else None
        except (TypeError, ValueError):
            min_pct = None
        try:
            max_pct = float(raw["max_pct"]) if raw.get("max_pct") is not None else None
        except (TypeError, ValueError):
            max_pct = None
        if min_pct is None and max_pct is None:
            return None
        return {"min_pct": min_pct, "max_pct": max_pct}

    try:
        min_risk_reward_filter = float(entry["min_risk_reward_filter"]) if entry.get("min_risk_reward_filter") is not None else None
    except (TypeError, ValueError):
        min_risk_reward_filter = None
    try:
        primary_target_lookback_bars = int(entry["primary_target_lookback_bars"]) if entry.get("primary_target_lookback_bars") is not None else None
        if primary_target_lookback_bars is not None and primary_target_lookback_bars <= 0:
            primary_target_lookback_bars = None
    except (TypeError, ValueError):
        primary_target_lookback_bars = None

    partial_tp = entry.get("partial_take_profit")
    partial_take_profit = None
    if isinstance(partial_tp, dict):
        try:
            trigger_rr = float(partial_tp["trigger_rr"]) if partial_tp.get("trigger_rr") is not None else None
            close_fraction = float(partial_tp["close_fraction"]) if partial_tp.get("close_fraction") is not None else None
        except (TypeError, ValueError):
            trigger_rr = close_fraction = None
        if trigger_rr is not None and close_fraction is not None and 0 < close_fraction < 1:
            partial_take_profit = {"trigger_rr": trigger_rr, "close_fraction": close_fraction}

    return {
        "name": str(entry.get("name") or "").strip(),
        "timeframes": timeframes,
        "indicators": indicators,
        "concepts_used": _clean_str_list(entry.get("concepts_used")),
        "entry_conditions": _conditions("entry_conditions"),
        "long_entry_conditions": _conditions("long_entry_conditions"),
        "short_entry_conditions": _conditions("short_entry_conditions"),
        "entry_rule_groups": _rule_groups(),
        "exit_conditions": _conditions("exit_conditions"),
        "confirmation_conditions": _conditions("confirmation_conditions"),
        "stop_loss": _clean_sltp(entry.get("stop_loss")),
        "take_profit": _clean_sltp(entry.get("take_profit")),
        "risk_pct": risk_pct,
        "risk_reward": risk_reward,
        "session_filter": [s for s in _clean_str_list(entry.get("session_filter")) if s in KNOWN_SESSIONS],
        "trend_filter": trend_filter,
        "day_filter": [d for d in _clean_str_list(entry.get("day_filter")) if d in KNOWN_DAYS],
        "breakeven_at_rr": breakeven_at_rr,
        "entry_type": entry_type,
        "entry_price_offset_pct": entry_price_offset_pct,
        "sl_distance_filter_pct": _pct_range_filter("sl_distance_filter_pct"),
        "min_risk_reward_filter": min_risk_reward_filter,
        "primary_target_lookback_bars": primary_target_lookback_bars,
        "partial_take_profit": partial_take_profit,
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


# ================================================================
# Batch 3, Task 1: Multi-Pass Extraction with Rule Counting
# ================================================================
# Replaces one combined extraction call with: an inventory call (count +
# list every distinct rule, no extraction), three scope-restricted
# extraction passes, and a comparison call (which inventory rules ended
# up captured). Motivation: Batch 2 found that a single combined call
# regularly drops most of a document's rules (PDH-PDL: 2 conditions
# captured out of 6+ real rules) -- a narrowly-scoped pass with less to
# track at once drops far fewer.

RULE_CATEGORIES = ["entry", "exit", "filters"]


def build_rule_inventory_prompt():
    """A deliberately NARROW prompt -- list and count, never extract. The
    smaller the job, the more reliable the count; this call's only
    purpose is producing a checklist the rest of the pipeline is graded
    against, so it must not silently merge/drop/summarize rules the way a
    combined extraction call has been shown to."""
    return (
        "You are building a CHECKLIST, not extracting a strategy. Read the "
        "document and list EVERY distinct trading rule it states -- every "
        "entry condition, every exit condition, every stop-loss rule, "
        "every take-profit rule, every filter/discard condition, every "
        "risk or position-sizing rule. Do NOT combine multiple rules into "
        "one list item, and do NOT skip a rule because it looks similar "
        "to another one already listed -- if the document states it as a "
        "separate sentence/clause, it is a separate rule.\n\n"
        "For EACH rule, quote the exact original text (do not paraphrase, "
        "do not summarize -- copy the words as written, trimmed to just "
        "that rule's clause/sentence) and classify it into exactly one "
        "category:\n"
        "  \"entry\" -- an entry condition or entry trigger\n"
        "  \"exit\" -- an exit rule, stop-loss rule, or take-profit rule\n"
        "  \"filters\" -- a filter/discard condition, or a risk/position-"
        "sizing rule (session/day restrictions, minimum RR, distance "
        "filters, partial exits, etc.)\n\n"
        "If the document has no trading strategy at all (pure lesson/"
        "psychology/notes content), return an empty rules list -- never "
        "invent a rule that isn't there.\n\n"
        "Respond with ONLY this JSON shape, no other text:\n"
        "{\n"
        '  "rules": [{"text": "<exact original wording>", "category": "entry"|"exit"|"filters"}]\n'
        "}\n"
    )


def parse_rule_inventory_response(raw_text):
    """Never raises. Returns {"rules": [{"id", "text", "category"}], "count"}
    or None if the response had no parseable JSON."""
    data = _parse_json_object(raw_text)
    if not isinstance(data, dict):
        return None
    raw_rules = data.get("rules")
    if not isinstance(raw_rules, list):
        return None
    rules = []
    for r in raw_rules:
        if not isinstance(r, dict):
            continue
        text = str(r.get("text") or "").strip()
        if not text:
            continue
        category = str(r.get("category") or "").strip().lower()
        # An unrecognized category label must never cause a real rule to
        # be dropped from the checklist -- default it to "entry" rather
        # than discard, so it still counts towards the expected total.
        if category not in RULE_CATEGORIES:
            category = "entry"
        rules.append({"id": len(rules) + 1, "text": text, "category": category})
    return {"rules": rules, "count": len(rules)}


_SCOPE_INSTRUCTIONS = {
    "entry": (
        "FOCUSED PASS -- ENTRY RULES ONLY.\n"
        "Populate ONLY: entry_conditions, long_entry_conditions, "
        "short_entry_conditions, entry_rule_groups, indicators needed for "
        "those conditions, concepts_used needed for those conditions, "
        "timeframes, entry_type, entry_price_offset_pct, name.\n"
        "Leave EVERY other field at its safe default exactly as if that "
        "part of the document didn't exist: exit_conditions=[], "
        "confirmation_conditions=[], stop_loss={\"type\":\"unknown\"}, "
        "take_profit={\"type\":\"unknown\"}, risk_pct=null, "
        "risk_reward=null, session_filter=[], trend_filter=null, "
        "day_filter=[], breakeven_at_rr=null, "
        "sl_distance_filter_pct=null, min_risk_reward_filter=null, "
        "primary_target_lookback_bars=null, partial_take_profit=null. Do "
        "NOT try to be helpful by also filling those in -- another "
        "focused pass handles them, and populating them here risks "
        "double-counting or drift between passes."
    ),
    "exit": (
        "FOCUSED PASS -- EXIT RULES, STOP-LOSS, AND TAKE-PROFIT ONLY.\n"
        "Populate ONLY: exit_conditions, confirmation_conditions, "
        "stop_loss, take_profit, breakeven_at_rr, name.\n"
        "Leave EVERY other field at its safe default exactly as if that "
        "part of the document didn't exist: entry_conditions=[], "
        "long_entry_conditions=[], short_entry_conditions=[], "
        "entry_rule_groups=[], entry_type=\"market\", "
        "entry_price_offset_pct=null, risk_pct=null, risk_reward=null "
        "(UNLESS risk_reward is only ever used to compute take_profit "
        "type \"rr\" -- then it belongs here), session_filter=[], "
        "trend_filter=null, day_filter=[], sl_distance_filter_pct=null, "
        "min_risk_reward_filter=null, primary_target_lookback_bars=null, "
        "partial_take_profit=null. Do NOT try to be helpful by also "
        "filling those in -- another focused pass handles them."
    ),
    "filters": (
        "FOCUSED PASS -- FILTERS, DISCARD CONDITIONS, AND RISK/POSITION-"
        "SIZING RULES ONLY.\n"
        "Populate ONLY: sl_distance_filter_pct, min_risk_reward_filter, "
        "primary_target_lookback_bars, partial_take_profit, risk_pct, "
        "session_filter, trend_filter, day_filter, name, and any "
        "candle_range_pct-type condition (a percent-range requirement on "
        "a candle's own size) -- put those inside entry_conditions ONLY "
        "if they are themselves filter/discard conditions, not ordinary "
        "entry triggers.\n"
        "Leave EVERY other field at its safe default exactly as if that "
        "part of the document didn't exist: entry_conditions=[] (except "
        "the candle_range_pct case above), long_entry_conditions=[], "
        "short_entry_conditions=[], entry_rule_groups=[], "
        "exit_conditions=[], confirmation_conditions=[], "
        "stop_loss={\"type\":\"unknown\"}, take_profit={\"type\":\"unknown\"}, "
        "risk_reward=null, entry_type=\"market\", "
        "entry_price_offset_pct=null, breakeven_at_rr=null. Do NOT try to "
        "be helpful by also filling those in -- another focused pass "
        "handles them."
    ),
}


def build_scoped_extraction_prompt(scope, source_hint=None, content_type=None):
    """scope: one of RULE_CATEGORIES ("entry" | "exit" | "filters"). Reuses
    the full structured-extraction prompt (same vocabulary, same JSON
    schema, same self-verification discipline) with a scope restriction
    prepended -- still returns the FULL JSON shape every time, just with
    everything outside `scope` left at its default, so a focused pass can
    be merged with the other two without needing to guess which fields it
    was even responsible for."""
    if scope not in _SCOPE_INSTRUCTIONS:
        raise ValueError(f"unknown extraction scope: {scope!r}")
    base = build_structured_extraction_prompt(source_hint, content_type)
    return f"{_SCOPE_INSTRUCTIONS[scope]}\n\n{'=' * 60}\n\n{base}"


def build_comparison_prompt(rule_inventory, captured_summary):
    """rule_inventory: the parsed dict from parse_rule_inventory_response
    (a numbered checklist). captured_summary: a plain-text/JSON summary of
    what the three focused passes actually produced (entry/exit/filter
    conditions, stop_loss/take_profit, etc.) -- built by
    ai_integration.multi_pass_extraction. Asks the AI to do the fuzzy
    matching a human would do: read each checklist rule and decide if the
    captured strategy actually represents it."""
    rules_text = "\n".join(f"{r['id']}. [{r['category']}] {r['text']}" for r in rule_inventory.get("rules", []))
    return (
        "You are auditing a strategy extraction for completeness. Below is "
        "a numbered CHECKLIST of every rule the original document stated, "
        "and a summary of what was actually captured into the executable "
        "strategy.\n\n"
        f"CHECKLIST:\n{rules_text}\n\n"
        f"CAPTURED:\n{captured_summary}\n\n"
        "For EACH checklist item, decide: is this rule genuinely "
        "represented in what was captured (even if reworded/mapped onto "
        "different vocabulary), or is it missing? Be strict -- a rule "
        "that's only PARTLY captured (e.g. the entry condition is there "
        "but a numeric filter attached to it isn't) counts as missing for "
        "that filter, not captured just because something related exists.\n\n"
        "IMPORTANT -- the person reading \"captured_as\" has NO trading "
        "background and will never see this codebase's internal names. "
        "Write it as one short, plain, everyday ROMAN URDU / HINGLISH "
        "sentence (the natural spoken mix, not formal/literary Urdu, not "
        "raw English jargon) describing in simple words what the system "
        "actually does for this rule -- e.g. \"Jab price PDH se upar "
        "jaaye to system yeh dekhta hai\" instead of naming a condition "
        "type, field name, or internal identifier. Never write a raw "
        "internal term (like a condition type name or field name) in "
        "this description -- describe the BEHAVIOR in plain words a "
        "non-trader would understand.\n\n"
        "Respond with ONLY this JSON shape, no other text:\n"
        "{\n"
        '  "results": [{"rule_id": <number>, "status": "captured"|"missing", '
        '"captured_as": "<one short Roman Urdu/Hinglish sentence in plain words, or null if missing>"}]\n'
        "}\n"
    )


def build_retry_prompt(missing_rules, source_hint=None, content_type=None):
    """(Batch 3, Task 2) A targeted follow-up call naming the SPECIFIC
    rules a previous pass missed, with their exact original text --
    never a generic "try again", always scoped to exactly what's still
    missing. missing_rules: list of {id, text, category} (a subset of a
    rule_inventory's rules)."""
    rules_text = "\n".join(f"{r['id']}. [{r['category']}] {r['text']}" for r in missing_rules)
    base = build_structured_extraction_prompt(source_hint, content_type)
    return (
        "TARGETED RETRY -- a previous extraction pass over this same "
        "document MISSED the following specific rules. Your ONLY job "
        "this time is to map THESE EXACT rules (and only these) into "
        "the schema below -- every other rule in the document has "
        "already been captured by a previous pass; do not re-extract "
        "anything else, even if you notice something you'd otherwise "
        "want to capture.\n\n"
        f"MISSING RULES TO RECOVER:\n{rules_text}\n\n"
        "Re-read the document specifically looking for these. If, after "
        "genuinely trying, one of these rules truly has no "
        "representation in the executable vocabulary below, LEAVE IT "
        "OUT -- do not force a mapping, do not guess, do not invent a "
        "condition just to fill the gap. An honestly-empty result for a "
        "rule you cannot map is correct; a fabricated one is not.\n\n"
        f"{'=' * 60}\n\n{base}"
    )


def parse_comparison_response(raw_text):
    """Never raises. Returns {"results": [{"rule_id", "status", "captured_as"}]}
    or None if the response had no parseable JSON."""
    data = _parse_json_object(raw_text)
    if not isinstance(data, dict):
        return None
    raw_results = data.get("results")
    if not isinstance(raw_results, list):
        return None
    results = []
    for r in raw_results:
        if not isinstance(r, dict):
            continue
        try:
            rule_id = int(r.get("rule_id"))
        except (TypeError, ValueError):
            continue
        status = str(r.get("status") or "").strip().lower()
        if status not in ("captured", "missing"):
            status = "missing"  # never silently assume captured on a malformed status
        captured_as = r.get("captured_as")
        results.append({
            "rule_id": rule_id, "status": status,
            "captured_as": str(captured_as).strip() if captured_as else None,
        })
    return {"results": results}


# ================================================================
# Batch 5, Task 1: Sentence-Level Extraction
# ================================================================
# Replaces the whole-document (or whole-scope) extraction call with one
# narrow call PER deterministically-identified candidate statement
# (ai_integration.deterministic_rules.count_candidate_rules) -- Batch 3's
# multi-pass approach still handed the AI a full document per pass, which
# measured as where real rules kept getting silently dropped (PDH-PDL 9/19,
# Liquidity Sweep & FVG 0/24). A single isolated sentence is a far smaller,
# more answerable question than "find everything in this document."

def build_statement_extraction_prompt(source_hint=None, content_type=None):
    """A DELIBERATELY CONDENSED schema prompt for sentence-level extraction
    (Batch 5, Task 1) -- unlike build_scoped_extraction_prompt (which reuses
    the full ~6,200-token whole-document prompt verbatim per pass), this one
    is a short-form reference of the same vocabulary/JSON shape, since it is
    sent on EVERY single-statement call. Measured real cost of reusing the
    full prompt per statement: it exhausted an entire day's provider token
    quota partway through extracting ONE 27-statement document. This
    condensed version keeps the vocabulary, the condition schema, and the
    "commit, don't hedge into raw" instruction; it drops the full prompt's
    extensive worked-examples list and 5-point self-verification block,
    which matter far less when the AI is only ever judging one short,
    already-isolated statement rather than reasoning over a whole document."""
    indicators_list = ", ".join(KNOWN_INDICATORS)
    sessions_list = ", ".join(KNOWN_SESSIONS)
    return (
        "SENTENCE-LEVEL EXTRACTION -- you will be given exactly ONE isolated "
        "statement/line from a larger trading strategy document, not the "
        "whole document. First decide: does this statement state or imply a "
        "concrete, executable trading rule (entry, exit, stop-loss/take-"
        "profit, a numeric filter, a session/day restriction, a risk rule)? "
        "Or is it a heading, disclaimer, or commentary with no executable "
        "content?\n\n"
        "If it IS a rule, map ONLY what this one statement states into the "
        "schema below -- do not invent context you were not shown. Commit to "
        "the closest vocabulary match rather than hedging into type=\"raw\" "
        "(e.g. \"previous day's high\"/\"PDH\" -> concept \"pdh\"; \"green/"
        "bullish candle\" -> direction \"bullish\"; \"breaks/crosses above\" "
        "a level -> that level's concept). Use type=\"raw\" with the exact "
        "\"text\" only when there is genuinely no vocabulary equivalent. "
        "Never fabricate a number or fact not in this statement or ordinary "
        "trading logic.\n\n"
        f"Indicators/concepts: {indicators_list}\n"
        f"Sessions: {sessions_list}\n"
        f"Timeframe roles: {', '.join(KNOWN_TIMEFRAME_ROLES)}\n"
        f"Stop-loss/take-profit types: {', '.join(KNOWN_SLTP_TYPES)}\n\n"
        f"{_CONDITION_SCHEMA_NOTE}\n\n"
        "A stop-loss/take-profit rule goes in the stop_loss/take_profit "
        "fields, never in exit_conditions. A day-of-week rule goes in the "
        "top-level day_filter list, not a condition. Session filters go in "
        "session_filter.\n\n"
        "Respond with ONLY this JSON, no other text:\n"
        '{"is_rule": true|false, "strategy": {\n'
        '  "name": "", "timeframes": {}, "indicators": [], "concepts_used": [],\n'
        '  "entry_conditions": [<condition>], "long_entry_conditions": [<condition>], '
        '"short_entry_conditions": [<condition>],\n'
        '  "entry_rule_groups": [], "exit_conditions": [<condition>], "confirmation_conditions": [],\n'
        '  "stop_loss": {"type": "fixed_pct|atr_multiple|structure|rr|level|signal_candle|unknown", '
        '"value": null, "level": null},\n'
        '  "take_profit": {"type": "fixed_pct|atr_multiple|structure|rr|level|signal_candle|unknown", '
        '"value": null, "level": null},\n'
        '  "risk_pct": null, "risk_reward": null, "session_filter": [], "trend_filter": null, '
        '"day_filter": [],\n'
        '  "breakeven_at_rr": null, "entry_type": "market", "entry_price_offset_pct": null,\n'
        '  "sl_distance_filter_pct": null, "min_risk_reward_filter": null, '
        '"primary_target_lookback_bars": null, "partial_take_profit": null\n'
        "}}\n\n"
        "If is_rule is false, still return this exact shape with every strategy field left empty/null."
    )


def parse_statement_response(raw_text):
    """Never raises. Returns {"is_rule": bool, "strategy": dict|None} or
    None if the response had no parseable JSON at all."""
    data = _parse_json_object(raw_text)
    if not isinstance(data, dict):
        return None
    is_rule = bool(data.get("is_rule"))
    strategy = _clean_strategy(data.get("strategy")) if is_rule else None
    return {"is_rule": is_rule, "strategy": strategy}
