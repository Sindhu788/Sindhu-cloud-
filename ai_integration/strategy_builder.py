"""AI Knowledge Learning Engine (v7) -- turns a validated, vocabulary-
sanitized AI structured-extraction dict (ai_integration.schema.
parse_structured_response()) directly into real StrategyConfig/Condition/
SLTPSpec/Lesson objects. This is the module that replaces the old regex
pipeline (knowledge_compiler.rule_extractor / backtest_engine.strategy_parser
/ knowledge_compiler.lesson_extractor) for the AI-assisted import path -- AI
output is NEVER routed back through those modules.

Every condition is still checked against the backtest engine's real
executable vocabulary (backtest_engine.validator._KNOWN_INDICATORS,
strategy_parser.SESSION_NAMES) before being trusted: anything outside that
vocabulary is demoted to type="raw" (recognized as present but not
executable, exactly like the old parser's own "raw" fallback for text it
couldn't confidently classify) rather than being passed through as a fake
executable primitive that could misbehave inside the backtest engine.
"""

import uuid
from datetime import datetime, timezone

from backtest_engine.strategy_config import Condition, SLTPSpec, StrategyConfig
from backtest_engine.validator import normalize_timeframes
from knowledge_engine.lesson import Lesson

from ai_integration.schema import KNOWN_INDICATORS, KNOWN_SESSIONS, KNOWN_SLTP_TYPES
# Single source of truth for "which concepts_used entry makes a given
# concept condition computable" -- backtest_engine.validator uses this
# exact table to DETECT the gap; importing it here (rather than keeping a
# second copy) means the repair below can never quietly drift out of sync
# with what the validator actually checks.
from backtest_engine.validator import _CONCEPT_REQUIRES_ANY_OF, _STRUCTURE_SL_SOURCES
# Same backfill the deterministic parser always runs on itself
# (strategy_parser.parse_strategy_text -> _ensure_indicators_for_conditions)
# -- reused here rather than reimplemented so the two pipelines can't drift.
# repair_condition_roles() is the same idea for Condition.role: the AI is
# asked to self-report which timeframe a concept condition belongs to
# (schema.py's _CONDITION_SCHEMA_NOTE), but doesn't reliably follow that
# instruction in practice -- this deterministically re-derives it from the
# document's own raw_text afterward, regardless of what the AI did or
# didn't say.
from backtest_engine.strategy_parser import _ensure_indicators_for_conditions, repair_condition_roles

_KNOWN_INDICATOR_SET = set(KNOWN_INDICATORS)
_KNOWN_SESSION_SET = set(KNOWN_SESSIONS)

# ConfiguredStrategy._compute_stop_loss() resolves a "structure" stop from
# an order-block zone, then an FVG zone, then plain swing support/
# resistance. If concepts_used names none of these, prepare_context()
# computes no zone column at all and the stop can never be calculated.
_STRUCTURAL_CONCEPTS = _STRUCTURE_SL_SOURCES
# The guaranteed fallback pair that _compute_stop_loss() always ends on.
_STRUCTURAL_FALLBACK = ("support", "resistance")
_SLTP_TYPE_WORDS = {t.lower() for t in KNOWN_SLTP_TYPES}


def _is_degenerate_raw(cond):
    """True for a raw condition carrying no actual rule -- empty text, or
    text that is merely a stop-loss/take-profit TYPE name. Models
    occasionally echo the SL/TP type into exit_conditions (e.g. an exit
    condition whose entire text is "structure"), which is not a market
    event to exit on; it just re-states a field that already exists. Left
    in place it registers as an unclear exit rule and sends an otherwise
    complete strategy to clarification for nothing."""
    if cond is None or cond.type != "raw":
        return False
    text = (cond.text or "").strip().lower()
    return not text or text in _SLTP_TYPE_WORDS


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _describe_raw(cond_dict):
    """A human-readable fallback description for a condition being demoted
    to type='raw', so nothing is silently lost even when the AI's proposed
    vocabulary doesn't match what the backtest engine can execute."""
    if cond_dict.get("text"):
        return cond_dict["text"]
    parts = [str(v) for v in (
        cond_dict.get("indicator"), cond_dict.get("op"), cond_dict.get("value"),
        cond_dict.get("indicator2"), cond_dict.get("name"), cond_dict.get("direction"),
    ) if v is not None]
    return " ".join(parts) or "unrecognized condition"


def build_condition(cond_dict):
    """cond_dict: already type/op/value-sanitized by schema._clean_condition.
    Returns a real Condition, demoting to type='raw' if the indicator/
    concept/session name isn't in the backtest engine's known vocabulary --
    never raises, never invents an executable primitive that doesn't exist."""
    if not cond_dict:
        return None
    cond_type = cond_dict.get("type", "raw")

    if cond_type in ("indicator_compare", "price_compare"):
        indicator = cond_dict.get("indicator")
        # indicator_compare compares the indicator to a fixed NUMBER
        # (cond.value) -- there's no way to express "ema20 > ema50"
        # (indicator vs. indicator) with this type, but the AI sometimes
        # tries anyway, submitting one with no value. That used to reach
        # the engine as a real, "executable" Condition that crashed at
        # eval time (TypeError comparing a float to None); now it's
        # demoted to raw here, same as any other rule this vocabulary
        # can't represent -- price_compare doesn't use cond.value at all
        # (it compares price to the indicator directly) so it's unaffected.
        missing_value = cond_type == "indicator_compare" and cond_dict.get("value") is None
        if not indicator or indicator not in _KNOWN_INDICATOR_SET or cond_dict.get("op") not in (">", "<") or missing_value:
            return Condition(type="raw", text=_describe_raw(cond_dict))
        return Condition(
            type=cond_type, indicator=indicator, params=cond_dict.get("params") or {},
            op=cond_dict.get("op"), value=cond_dict.get("value"),
            lookback_bars=cond_dict.get("lookback_bars"),
        )

    if cond_type == "indicator_vs_indicator":
        indicator = cond_dict.get("indicator")
        indicator2 = cond_dict.get("indicator2")
        if (not indicator or not indicator2 or indicator not in _KNOWN_INDICATOR_SET
                or indicator2 not in _KNOWN_INDICATOR_SET or cond_dict.get("op") not in (">", "<")):
            return Condition(type="raw", text=_describe_raw(cond_dict))
        return Condition(
            type="indicator_vs_indicator", indicator=indicator, params=cond_dict.get("params") or {},
            op=cond_dict.get("op"), indicator2=indicator2, params2=cond_dict.get("params2") or {},
            role=cond_dict.get("role"),
        )

    if cond_type == "concept":
        name = cond_dict.get("name")
        if not name or name not in _KNOWN_INDICATOR_SET:
            return Condition(type="raw", text=_describe_raw(cond_dict))
        return Condition(
            type="concept", name=name, direction=cond_dict.get("direction"),
            lookback_bars=cond_dict.get("lookback_bars"), role=cond_dict.get("role"),
        )

    if cond_type == "session":
        name = cond_dict.get("name")
        if not name or name not in _KNOWN_SESSION_SET:
            return Condition(type="raw", text=_describe_raw(cond_dict))
        return Condition(type="session", name=name)

    if cond_type == "trend":
        direction = cond_dict.get("direction")
        if direction not in ("bullish", "bearish"):
            return Condition(type="raw", text=_describe_raw(cond_dict))
        return Condition(type="trend", direction=direction)

    return Condition(type="raw", text=_describe_raw(cond_dict))


def build_stop_loss_take_profit(sltp_dict):
    """sltp_dict: already type-sanitized by schema._clean_sltp (a real
    SLTPSpec-compatible dict). type="rr" without a value, or type="level"
    without a level, are semantically incomplete -- demoted to "unknown"
    rather than trusted half-built, same conservatism as the old validator."""
    sltp_type = sltp_dict.get("type", "unknown")
    value = sltp_dict.get("value")
    level = sltp_dict.get("level")
    if sltp_type in ("fixed_pct", "atr_multiple", "rr") and value is None:
        return SLTPSpec(type="unknown")
    if sltp_type == "level" and not level:
        return SLTPSpec(type="unknown")
    return SLTPSpec(type=sltp_type, value=value, level=level)


def build_strategy_config(ai_strategy, name, raw_text):
    """ai_strategy: the sanitized "strategy" sub-dict from
    schema.parse_structured_response() (never None -- caller checks that
    first). Returns a real StrategyConfig, directly machine-readable by the
    backtest engine -- no text re-parsing anywhere in this path."""
    def _conditions(key):
        built = [c for c in (build_condition(c) for c in ai_strategy.get(key) or []) if c]
        # Strip rules that carry no information (see _is_degenerate_raw) --
        # keeping them only produces a spurious "unclear rule" that sends an
        # otherwise-complete strategy to clarification.
        return [c for c in built if not _is_degenerate_raw(c)]

    def _rule_groups():
        groups = []
        for g in ai_strategy.get("entry_rule_groups") or []:
            conditions = [c for c in (build_condition(c) for c in g.get("conditions") or []) if c]
            conditions = [c for c in conditions if not _is_degenerate_raw(c)]
            if not conditions:
                continue
            groups.append({"label": g.get("label") or "", "direction": g.get("direction"), "conditions": conditions})
        return groups

    # Normalize AI-reported timeframe strings ("daily" -> "1d", "hourly" ->
    # "1h", ...) to exactly what the resampler accepts (data_engine.config.
    # SUPPORTED_INTERVALS) -- validator.normalize_timeframes() already
    # existed for this (the deterministic text-parser path calls it via
    # sindhu_web/api/backtesting.py's /parse endpoint), but was never wired
    # into the AI-native path, so an AI-reported "daily"/"5m/15m" reached
    # MultiTimeframeContext unnormalized and crashed the backtest outright
    # with a raw "Unsupported interval" exception instead of failing
    # cleanly at validation. Unrecognized strings are left untouched (same
    # as before) so validate() still reports them, rather than silently
    # guessing.
    normalized_timeframes, _ = normalize_timeframes(ai_strategy.get("timeframes") or {})

    config = StrategyConfig(
        name=ai_strategy.get("name") or name or "Unnamed Strategy",
        raw_text=raw_text,
        timeframes=normalized_timeframes,
        indicators=list(ai_strategy.get("indicators") or []),
        concepts_used=list(ai_strategy.get("concepts_used") or []),
        entry_conditions=_conditions("entry_conditions"),
        long_entry_conditions=_conditions("long_entry_conditions"),
        short_entry_conditions=_conditions("short_entry_conditions"),
        entry_rule_groups=_rule_groups(),
        exit_conditions=_conditions("exit_conditions"),
        confirmation_conditions=_conditions("confirmation_conditions"),
        stop_loss=build_stop_loss_take_profit(ai_strategy.get("stop_loss") or {}),
        take_profit=build_stop_loss_take_profit(ai_strategy.get("take_profit") or {}),
        risk_pct=ai_strategy.get("risk_pct"),
        risk_reward=ai_strategy.get("risk_reward"),
        session_filter=list(ai_strategy.get("session_filter") or []),
        trend_filter=ai_strategy.get("trend_filter"),
        day_filter=list(ai_strategy.get("day_filter") or []),
        breakeven_at_rr=ai_strategy.get("breakeven_at_rr"),
    )
    sync_concepts_used(config)
    _repair_structural_stop(config)
    # The AI can emit a price_compare/indicator_compare condition (e.g.
    # "price < vwap") without also declaring a matching entries in
    # `indicators` -- config.indicators is what actually tells
    # ConfiguredStrategy.prepare_context() which column to compute, so an
    # undeclared indicator means the condition silently evaluates False
    # forever (found live: "Five A+ iFVG Setups" had a `vwap` price_compare
    # condition with `indicators: []`). The deterministic text parser
    # already self-heals this via the same helper; the AI-native path had no
    # equivalent safety net until now.
    _ensure_indicators_for_conditions(config)
    repair_condition_roles(config)
    return config


def sync_concepts_used(config):
    """General, permanent repair for the most common false "Needs
    Clarification" verdict: a condition (entry/exit/confirmation) correctly
    references a supported concept (candle_break, bos, choch, fvg, pdh,
    pdl, support, resistance, liquidity_sweep, order_block, breaker_block,
    volume, pdh_sweep, pdl_sweep), but concepts_used was never updated to
    match. concepts_used is what actually tells ConfiguredStrategy.
    prepare_context() which columns to compute -- a concept named only
    inside a condition, and nowhere in concepts_used, can never evaluate
    true, so the AI's own (already-correct) interpretation silently never
    fires. validator._CONCEPT_REQUIRES_ANY_OF is exactly the gate table
    prepare_context() implements, so this repair registers concepts_used
    entries whenever a condition's gate isn't already satisfied.

    This is pure bookkeeping: it registers the SAME concept the condition
    already names (never a different one, never invents a rule), so it
    cannot change what the strategy means -- it only lets the engine
    compute what was already asked for. A concept name that isn't in
    _CONCEPT_REQUIRES_ANY_OF at all (an indicator name, or genuinely
    unsupported vocabulary) is left completely untouched; validate()'s
    "Invalid indicator/concept" check is what correctly flags that as a
    real, different problem that still needs clarification.

    Called automatically for every AI-assisted import (from
    build_strategy_config above), and also safe to re-run against any
    already-saved StrategyConfig as a one-time backfill -- it's a pure
    no-op once concepts_used already satisfies every condition. Mutates
    config.concepts_used in place; returns True if anything changed."""
    concepts_used_set = set(config.concepts_used)
    changed = False
    all_condition_buckets = [getattr(config, n) for n in
                              ("entry_conditions", "long_entry_conditions", "short_entry_conditions",
                               "exit_conditions", "confirmation_conditions")]
    all_condition_buckets += [g.get("conditions") or [] for g in config.entry_rule_groups]
    for bucket in all_condition_buckets:
        for cond in bucket:
            if cond.type != "concept" or cond.name not in _CONCEPT_REQUIRES_ANY_OF:
                continue
            required_any = _CONCEPT_REQUIRES_ANY_OF[cond.name]
            if required_any & concepts_used_set:
                continue
            concepts_used_set.add(cond.name)
            changed = True
    if changed:
        config.concepts_used = sorted(concepts_used_set)
    return changed


def _repair_structural_stop(config):
    """A "structure" stop/target is only computable if some structural zone
    is actually built for the frame. The AI can name the stop TYPE correctly
    while forgetting to list the concept the zone comes from, which leaves a
    strategy that validates as "structure" but can never place a protected
    trade. Rather than send an otherwise-complete strategy to clarification
    over a bookkeeping omission, add the swing support/resistance pair --
    which is exactly the fallback _compute_stop_loss() already resolves to
    when no order-block or FVG zone is present, so this makes the config
    match the behaviour it was already going to get. Mutates in place; a
    strategy that already names a structural concept is left untouched."""
    uses_structure = config.stop_loss.type == "structure" or config.take_profit.type == "structure"
    if not uses_structure:
        return
    if _STRUCTURAL_CONCEPTS & set(config.concepts_used):
        return
    for concept in _STRUCTURAL_FALLBACK:
        if concept not in config.concepts_used:
            config.concepts_used.append(concept)


def build_lesson(ai_lesson):
    """ai_lesson: a sanitized lesson dict from schema.parse_structured_response()
    (title/category/description/tags/rule_type/direction/condition already
    validated). Constructs a real Lesson directly -- unlike
    knowledge_engine.lesson.new_lesson(), this never calls
    strategy_parser.parse_conditions() on the description text; AI already
    supplied rule_type/direction/condition directly, so nothing here
    re-derives them from keywords."""
    condition = build_condition(ai_lesson.get("condition")) if ai_lesson.get("condition") else None
    conditions = [condition] if condition and condition.type != "raw" else []
    now = _now_iso()
    return Lesson(
        id=uuid.uuid4().hex[:12],
        title=ai_lesson["title"], category=ai_lesson["category"], description=ai_lesson["description"],
        priority="Medium", status="active",
        notes="Auto-extracted by the AI Knowledge Learning Engine (v7 structured extraction).",
        apply_backtesting=True, apply_paper_trading=True, apply_evolution=True,
        rule_type=ai_lesson.get("rule_type") or "block_if_true",
        direction=ai_lesson.get("direction"),
        conditions=conditions,
        created_at=now, updated_at=now, version=1,
        tags=ai_lesson.get("tags") or [],
    )
