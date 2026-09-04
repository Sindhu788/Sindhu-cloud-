"""Open Position Manager + Trade Monitor + Trade Close. Owns the
lifecycle from "approved candidate" to "closed, reflected-on trade,"
including automatic Trade Tagging and the per-stage lifecycle timestamps
the spec asks for.
"""

import time
import uuid
from datetime import datetime, timezone

from backtest_engine.engine import _apply_slippage, EMERGENCY_STOP_PCT
from data_engine import storage, feature_toggles
from paper_trading import reflection, evolution, auto_avoid, drawdown_guard, telegram_bot, ai_trade_review
from paper_trading import account_drawdown_guard, profit_lock
from paper_trading import config as pt_config
from paper_trading.guards import book_key as _book_key
# Evolution Core Engine (Phase 7A, A.1): turns this closed trade's outcome,
# combined with this strategy's own trade history, into a traceable BOT
# lesson when a pattern is statistically meaningful. evolution_engine has no
# dependency back on paper_trading, so this import can never form a cycle.
from evolution_engine import lesson_generator


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def auto_tags(market_snapshot, timeframe):
    tags = []
    state = market_snapshot.get("market_state")
    if state in ("trending_up", "trending_down"):
        tags.append("Trend")
    if state == "breakout":
        tags.append("Breakout")
    if timeframe in ("1m", "3m", "5m", "15m"):
        tags.append("Scalping")
    elif timeframe in ("4h", "6h", "12h", "1d", "1w"):
        tags.append("Swing")
    session = market_snapshot.get("session")
    if session == "london":
        tags.append("London")
    elif session == "ny":
        tags.append("New York")
    if market_snapshot.get("volume_spike"):
        tags.append("High Volume")
    if market_snapshot.get("structure"):
        tags.append("Liquidity")
    return tags


def open_position(exchange, symbol, candidate, size, risk_amount, confidence, market_snapshot):
    position_id = uuid.uuid4().hex[:16]
    side = "long" if candidate["direction"] == "bullish" else "short"
    entry_price = _apply_slippage(candidate["entry_price"], side, False, 0.0005)
    now_ms = int(time.time() * 1000)
    now = _now_iso()

    # Same Requirement 20 re-validation backtest_engine._open_position()
    # applies: stop_loss/take_profit were computed against the raw signal
    # price before slippage, so re-check them against the real, slipped
    # entry_price and discard (rather than trust) one that ended up on the
    # wrong side. A missing stop_loss additionally gets the same emergency
    # fallback -- unlike backtesting, a live paper position has no "end of
    # data" bound, so a structure stop whose zone search found nothing
    # would otherwise ride completely unprotected indefinitely, not just
    # until a fixed dataset ends.
    stop_loss = candidate["stop_loss"]
    take_profit = candidate["take_profit"]
    stop_loss_type = candidate.get("stop_loss_type")
    if stop_loss is not None:
        wrong_side = (side == "long" and stop_loss >= entry_price) or (side == "short" and stop_loss <= entry_price)
        if wrong_side:
            stop_loss = None
    if stop_loss is None and stop_loss_type not in (None, "unknown"):
        stop_loss = entry_price * (1 - EMERGENCY_STOP_PCT) if side == "long" else entry_price * (1 + EMERGENCY_STOP_PCT)
    if take_profit is not None:
        wrong_side = (side == "long" and take_profit <= entry_price) or (side == "short" and take_profit >= entry_price)
        if wrong_side:
            take_profit = None

    pos = {
        "id": position_id, "exchange": exchange, "symbol": symbol,
        "direction": side, "entry_price": entry_price,
        "stop_loss": stop_loss, "take_profit": take_profit,
        "size": size, "risk_amount": risk_amount, "entry_time": now_ms,
        "entry_reason": candidate["entry_reason"],
        "strategy_id": candidate.get("strategy_id"), "strategy_name": candidate.get("strategy_name"),
        "strategy_version": candidate.get("strategy_version"),
        "lesson_ids": candidate.get("lesson_ids", []), "confidence": confidence,
        "market_snapshot": market_snapshot, "tags": auto_tags(market_snapshot, candidate.get("timeframe")),
        "session": market_snapshot.get("session"), "timeframe": candidate.get("timeframe"),
        "market_state": market_snapshot.get("market_state"),
        "lifecycle": {
            "signal_detected": now, "signal_validated": now,
            "trade_reserved": now, "trade_opened": now,
        },
        "created_at": now,
    }
    storage.open_paper_position(pos)
    return pos


def _check_exit(position, latest_price, high=None, low=None):
    """Mirrors backtest_engine.engine._check_forced_exit(), which tests the
    bar's HIGH and LOW rather than a single price.

    Paper trading only samples a spot price once per tick (60s by default).
    Checking that spot price alone silently missed every stop-loss that was
    touched and then recovered between two ticks -- and since a stop sits
    much closer to entry than a 2.5:1 target does, those missed touches were
    overwhelmingly stop-losses, systematically inflating the paper win rate
    versus a backtest of the same strategy on the same data. Passing the
    latest closed candle's high/low makes both engines apply the same rule.

    high/low default to latest_price so any caller that genuinely has only a
    spot price (e.g. the orphaned-position ticker path) keeps working
    exactly as before. Stop-loss is checked before take-profit, same as the
    backtest, so a bar that spans both is recorded as the loss."""
    if high is None:
        high = latest_price
    if low is None:
        low = latest_price
    sl, tp = position["stop_loss"], position["take_profit"]
    if position["direction"] == "long":
        if sl is not None and low <= sl:
            return "stop_loss"
        if tp is not None and high >= tp:
            return "take_profit"
    else:
        if sl is not None and high >= sl:
            return "stop_loss"
        if tp is not None and low <= tp:
            return "take_profit"
    return None


def monitor_and_close(exchange, symbol, latest_price, high=None, low=None):
    """Trade Monitor + Trade Close: checked every tick for every coin that
    currently has an open position. `high`/`low` are the latest closed
    candle's range when the caller has it, so an intrabar stop/target touch
    is caught the same way the backtest catches it."""
    closed = []
    profit_lock_settings = None
    for pos in storage.get_open_paper_positions(exchange, symbol):
        # Grand Feature Expansion, Phase 3 Feature 8 (MAE/MFE): widen this
        # position's lowest/highest-price-seen range with this tick's
        # candle, BEFORE checking for exit -- an exit-triggering wick still
        # counts as part of this trade's real excursion history.
        tick_low = low if low is not None else latest_price
        tick_high = high if high is not None else latest_price
        storage.update_position_excursion(pos["id"], tick_low, tick_high)

        # Grand Feature Expansion, Phase 5 Feature 9: Profit-Lock Trailing
        # Stop -- reuses the excursion just widened above (pos's own
        # in-memory copy predates that write, so this tick's high/low is
        # folded in here too) to see if the stop should tighten BEFORE
        # this same tick's exit check runs.
        if profit_lock_settings is None:
            profit_lock_settings = pt_config.load()
        if profit_lock_settings.get("profit_lock_enabled", False):
            current_high = max(pos.get("highest_price_seen") or pos["entry_price"], tick_high)
            current_low = min(pos.get("lowest_price_seen") or pos["entry_price"], tick_low)
            new_stop = profit_lock.compute_trailing_stop(
                pos["direction"], pos["entry_price"], pos["stop_loss"], current_high, current_low,
                trigger_r=profit_lock_settings.get("profit_lock_trigger_r", 1.0),
                trail_pct=profit_lock_settings.get("profit_lock_trail_pct", 50.0),
            )
            if new_stop is not None:
                # Master Task 3, Phase 2.22: detect (never decide/act on)
                # the stop crossing to break-even-or-better for the FIRST
                # time, purely to notify Telegram -- no new trading logic,
                # just a comparison against the already-computed new_stop
                # and the position's own entry_price.
                old_stop = pos["stop_loss"]
                entry = pos["entry_price"]
                was_at_breakeven = (old_stop is not None) and (
                    old_stop >= entry if pos["direction"] == "long" else old_stop <= entry
                )
                now_at_breakeven = new_stop >= entry if pos["direction"] == "long" else new_stop <= entry
                storage.update_position_stop_loss(pos["id"], new_stop)
                pos["stop_loss"] = new_stop
                if now_at_breakeven and not was_at_breakeven:
                    try:
                        telegram_bot.send_breakeven_notification(pos)
                    except Exception:
                        pass  # informational only -- never let a notification failure affect trading

        reason = _check_exit(pos, latest_price, high, low)
        if reason:
            # Fill at the stop/target level itself, not the sampled spot
            # price -- again matching the backtest, which exits at sl/tp.
            fill = latest_price
            if reason == "stop_loss" and pos["stop_loss"] is not None:
                fill = pos["stop_loss"]
            elif reason == "take_profit" and pos["take_profit"] is not None:
                fill = pos["take_profit"]
            closed.append(_close(pos, fill, reason))
    return closed


def force_close(position_id, latest_price, reason="closed_manually"):
    pos = storage.get_paper_position(position_id)
    if not pos or pos["status"] != "open":
        return None
    return _close(pos, latest_price, reason)


def _close(pos, exit_price, exit_reason):
    exit_price = _apply_slippage(exit_price, pos["direction"], True, 0.0005)
    if pos["direction"] == "long":
        pnl = (exit_price - pos["entry_price"]) * pos["size"]
    else:
        pnl = (pos["entry_price"] - exit_price) * pos["size"]
    notional = pos["entry_price"] * pos["size"]
    pnl_pct = (pnl / notional * 100) if notional else 0.0
    now_ms = int(time.time() * 1000)
    now = _now_iso()

    lifecycle = dict(pos.get("lifecycle") or {})
    lifecycle["trade_managed"] = now
    lifecycle["trade_closed"] = now

    refl = reflection.build({**pos, "exit_time": now_ms}, exit_price, pnl, pnl_pct, exit_reason)
    lifecycle["reflection"] = now

    storage.close_paper_position(
        pos["id"], exit_price, now_ms, pnl, pnl_pct, exit_reason, lifecycle, refl, now,
        book_key=_book_key(pos),
    )

    closed_pos = {**pos, "exit_price": exit_price, "exit_time": now_ms, "pnl": pnl,
                  "pnl_pct": pnl_pct, "exit_reason": exit_reason, "reflection": refl}
    evolution.record_outcome(closed_pos, pnl, pnl_pct)
    lifecycle["evolution"] = _now_iso()
    generated_lessons = lesson_generator.analyze_and_generate_lessons(closed_pos, now)
    if generated_lessons:
        lifecycle["bot_lessons_generated"] = generated_lessons

    # Pattern-Based Auto-Avoid (Self-Learning Group, item 1): re-check this
    # exact pattern's consecutive-loss streak now that this close is
    # recorded. A pure read-then-audit-write side effect -- never touches
    # pnl/exit_price/anything already computed above.
    auto_avoid.evaluate_pattern(
        pos.get("strategy_id"), pos.get("strategy_name"), pos["symbol"],
        pos.get("market_state"), pos.get("session"),
    )
    # Drawdown Protection Engine (item 4): same read-then-audit-write shape,
    # strategy-scoped, never touches the pnl/exit values already computed above.
    # NOTE: only the write (deciding to pause) is gated here -- the READ that
    # blocks new trades on an already-paused strategy (engine.py's
    # storage.is_strategy_paused check) is intentionally never gated, so
    # turning this toggle off mid-pause can't silently resume a strategy
    # that's mid-drawdown.
    if feature_toggles.is_enabled("drawdown_protection_enabled"):
        drawdown_guard.evaluate_strategy(pos.get("strategy_id"), pos.get("strategy_name"))
        # Account-wide Drawdown Circuit-Breaker (Grand Feature Expansion,
        # Phase 1 Feature 5): same trigger point, but compares the COMBINED
        # balance across every book against its own peak -- see the
        # module's own docstring for why this is a separate, stricter,
        # system-wide check rather than a duplicate of the per-strategy one.
        account_drawdown_guard.evaluate_account()

    # A5: two-way Telegram awareness -- only sends if a signal was actually
    # sent for this exact position earlier (checked inside the function).
    try:
        telegram_bot.send_close_followup(closed_pos)
    except Exception:
        pass

    # AI Trade Review (B4): at most one AI call, OFF by default, never lets
    # an AI failure affect the trade close already fully recorded above.
    try:
        ai_trade_review.review_trade(closed_pos)
    except Exception:
        pass
    return closed_pos
