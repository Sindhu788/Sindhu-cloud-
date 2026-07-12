"""Decision Engine: produces trade candidates from two independent paths,
exactly as specified -- "a trade may execute if a valid Strategy matches
OR a valid Lesson matches" -- strategies and lessons never depend on each
other.

Strategy path: reuses backtest_engine.configured_strategy.ConfiguredStrategy
and backtest_engine.mtf_context.MultiTimeframeContext verbatim (the same
code the Backtesting Engine runs), evaluated at the latest closed bar
instead of walked bar-by-bar over history. Active lessons are checked
against that same prepared dataframe purely for tracking/logging (same as
KnowledgeEngine.check() in backtesting) -- a Lesson can never block or
modify a Strategy's own validated signal; Strategies and Lessons are
independent.

Lesson path: a lesson with rule_type="require_if_true" and a direction is
a complete, standalone signal on its own -- it gets its own indicator
frame (paper_trading.frame_builder) since no strategy is present to have
already computed one.
"""

import time

from backtest_engine.configured_strategy import ConfiguredStrategy
from backtest_engine.mtf_context import MultiTimeframeContext
from knowledge_engine.condition_eval import evaluate_condition

from paper_trading import frame_builder


def _lookback_start_ms(settings):
    """A fixed calendar window rather than a candle count, since roles in
    a multi-timeframe strategy can each be a different granularity --
    enough for indicator warmup (EMA/RSI/ATR/BOS/CHoCH) without reading
    more 1m rows than necessary from a database with tens of millions of
    them."""
    days = settings.get("lookback_days", 20)
    return int(time.time() * 1000) - days * 86400 * 1000


def _apply_lessons(df, i, direction, lessons):
    """Tracking only -- returns which lesson (if any) would have matched a
    block_if_true rule, purely for logging/display. Does NOT gate whether
    the strategy's candidate is approved; same recording semantics as
    KnowledgeEngine.check() but with no veto power, highest priority first,
    first matching lesson reported."""
    applied_ids = []
    for lesson in lessons:
        if lesson.direction and lesson.direction != direction:
            continue
        condition_true = all(evaluate_condition(df, i, c) for c in lesson.conditions)
        triggered = condition_true if lesson.rule_type == "block_if_true" else not condition_true
        applied_ids.append(lesson.id)
        if triggered:
            return f"{lesson.title} ({lesson.category})", applied_ids
    return None, applied_ids


def strategy_candidates(exchange, symbol, strategies, lessons, settings):
    candidates = []
    start_ms = _lookback_start_ms(settings)
    for s in strategies:
        cfg = s["config"]
        try:
            ctx = MultiTimeframeContext(exchange, symbol, cfg.timeframes, start_ms=start_ms)
        except ValueError:
            continue
        if ctx.is_empty():
            continue

        strat = ConfiguredStrategy(cfg)
        try:
            merged = strat.prepare_context(ctx)
            merged = strat.prepare(merged)
        except Exception:
            continue
        if merged.empty:
            continue

        i = len(merged) - 1
        try:
            signal = strat.on_bar(merged, i, position=None)
        except Exception:
            continue
        if signal is None or signal.action not in ("buy", "sell"):
            continue

        direction = "bullish" if signal.action == "buy" else "bearish"
        # veto_reason is recorded for tracking/display only (e.g. Reports
        # page visibility into which lessons matched) -- it never affects
        # "approved" below, since a Lesson must never block a Strategy's
        # own validated signal.
        veto_reason, applied_ids = _apply_lessons(merged, i, direction, lessons)

        candidates.append({
            "source": "strategy",
            "strategy_id": s["strategy_id"], "strategy_name": s["strategy_name"],
            "strategy_version": s.get("priority"),
            "direction": direction, "action": signal.action,
            "entry_price": float(merged["close"].iloc[i]),
            "stop_loss": signal.stop_loss, "take_profit": signal.take_profit,
            "entry_reason": signal.reason,
            "timeframe": cfg.timeframes.get("entry"),
            "approved": True, "veto_reason": veto_reason,
            "lesson_ids": applied_ids,
        })
    return candidates


def lesson_candidates(exchange, symbol, lessons, settings):
    require_lessons = [l for l in lessons if l.rule_type == "require_if_true" and l.direction]
    if not require_lessons:
        return []

    timeframe = settings.get("lesson_default_timeframe", "1h")
    start_ms = _lookback_start_ms(settings)
    df = frame_builder.build_entry_frame(exchange, symbol, timeframe, require_lessons, start_ms=start_ms)
    if df is None:
        return []
    i = len(df) - 1

    candidates = []
    sl_pct = settings.get("lesson_default_sl_pct", 2.0) / 100.0
    rr = settings.get("lesson_default_rr", 2.0)
    price = float(df["close"].iloc[i])

    for lesson in require_lessons:
        try:
            condition_true = all(evaluate_condition(df, i, c) for c in lesson.conditions)
        except Exception:
            continue
        if not condition_true:
            continue

        direction = lesson.direction
        sl = price * (1 - sl_pct) if direction == "bullish" else price * (1 + sl_pct)
        risk_distance = abs(price - sl)
        tp = price + risk_distance * rr if direction == "bullish" else price - risk_distance * rr

        candidates.append({
            "source": "lesson",
            "strategy_id": None, "strategy_name": None, "strategy_version": None,
            "direction": direction, "action": "buy" if direction == "bullish" else "sell",
            "entry_price": price, "stop_loss": sl, "take_profit": tp,
            "entry_reason": f"Lesson: {lesson.title}",
            "timeframe": timeframe,
            "approved": True, "veto_reason": None,
            "lesson_ids": [lesson.id], "lesson_title": lesson.title,
        })
    return candidates


def generate_candidates(exchange, symbol, strategies, lessons, settings):
    return strategy_candidates(exchange, symbol, strategies, lessons, settings) + \
        lesson_candidates(exchange, symbol, lessons, settings)
