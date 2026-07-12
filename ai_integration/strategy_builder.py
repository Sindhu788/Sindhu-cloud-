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
from knowledge_engine.lesson import Lesson

from ai_integration.schema import KNOWN_INDICATORS, KNOWN_SESSIONS

_KNOWN_INDICATOR_SET = set(KNOWN_INDICATORS)
_KNOWN_SESSION_SET = set(KNOWN_SESSIONS)


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _describe_raw(cond_dict):
    """A human-readable fallback description for a condition being demoted
    to type='raw', so nothing is silently lost even when the AI's proposed
    vocabulary doesn't match what the backtest engine can execute."""
    if cond_dict.get("text"):
        return cond_dict["text"]
    parts = [str(v) for v in (cond_dict.get("indicator"), cond_dict.get("op"), cond_dict.get("value"), cond_dict.get("name"), cond_dict.get("direction")) if v is not None]
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
        if not indicator or indicator not in _KNOWN_INDICATOR_SET or cond_dict.get("op") not in (">", "<"):
            return Condition(type="raw", text=_describe_raw(cond_dict))
        return Condition(
            type=cond_type, indicator=indicator, params=cond_dict.get("params") or {},
            op=cond_dict.get("op"), value=cond_dict.get("value"),
            lookback_bars=cond_dict.get("lookback_bars"),
        )

    if cond_type == "concept":
        name = cond_dict.get("name")
        if not name or name not in _KNOWN_INDICATOR_SET:
            return Condition(type="raw", text=_describe_raw(cond_dict))
        return Condition(type="concept", name=name, direction=cond_dict.get("direction"), lookback_bars=cond_dict.get("lookback_bars"))

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
    config = StrategyConfig(
        name=ai_strategy.get("name") or name or "Unnamed Strategy",
        raw_text=raw_text,
        timeframes=dict(ai_strategy.get("timeframes") or {}),
        indicators=list(ai_strategy.get("indicators") or []),
        concepts_used=list(ai_strategy.get("concepts_used") or []),
        entry_conditions=[c for c in (build_condition(c) for c in ai_strategy.get("entry_conditions") or []) if c],
        exit_conditions=[c for c in (build_condition(c) for c in ai_strategy.get("exit_conditions") or []) if c],
        confirmation_conditions=[c for c in (build_condition(c) for c in ai_strategy.get("confirmation_conditions") or []) if c],
        stop_loss=build_stop_loss_take_profit(ai_strategy.get("stop_loss") or {}),
        take_profit=build_stop_loss_take_profit(ai_strategy.get("take_profit") or {}),
        risk_pct=ai_strategy.get("risk_pct"),
        risk_reward=ai_strategy.get("risk_reward"),
        session_filter=list(ai_strategy.get("session_filter") or []),
        trend_filter=ai_strategy.get("trend_filter"),
    )
    return config


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
