"""Pattern-Based Auto-Avoid Rule (Self-Learning Group, item 1): when one
EXACT pattern -- a specific (strategy, symbol, market_state, session)
combination -- has lost CONSECUTIVE_LOSS_THRESHOLD times in a row, new
entries matching that exact pattern are suppressed going forward. This
never touches the strategy itself (it keeps trading every OTHER coin/market
condition normally) and never deletes anything -- it's a reversible,
fully-logged veto recorded in paper_auto_avoid_rules.

Threshold rationale: 5 consecutive losses under the identical condition is
the same bar the existing Drawdown Alert already uses for "worth a look"
(see paper_trading.insights.detect_alerts) -- reusing an established,
already-reasoned-about number rather than inventing a new one. With random
50/50 odds a 5-loss streak has a ~3% chance of happening by chance alone,
so it's a meaningful (not just noisy) signal, while still triggering fast
enough to matter within a strategy's first hundred trades.

Called after every trade close (see paper_trading.position_manager) --
cheap (one indexed query over one pattern's own trades, not a full scan)."""

from datetime import datetime, timezone

from data_engine import storage

CONSECUTIVE_LOSS_THRESHOLD = 5


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def evaluate_pattern(strategy_id, strategy_name, symbol, market_state, session, since=None):
    """Recomputes the consecutive-loss streak for this exact pattern and
    creates/refreshes the auto-avoid rule if the streak has reached the
    threshold, or does nothing if it hasn't (or has since recovered with a
    win -- a single win resets the streak, since the trigger is CONSECUTIVE
    losses, not total losses). Returns the rule reason string if a rule was
    (re)triggered this call, else None."""
    if not strategy_id or not symbol or not market_state or not session:
        return None  # degrade gracefully -- a lesson-only trade has no strategy_id to scope a rule to

    trades = storage.list_paper_pattern_trades_ordered(strategy_id, symbol, market_state, session, since=since)
    if len(trades) < CONSECUTIVE_LOSS_THRESHOLD:
        return None  # not enough samples yet for this exact pattern -- degrade gracefully, no false trigger

    streak = 0
    for t in reversed(trades):  # newest-first
        if t["pnl"] is not None and t["pnl"] < 0:
            streak += 1
        else:
            break

    if streak < CONSECUTIVE_LOSS_THRESHOLD:
        return None

    reason = (f"{strategy_name or strategy_id} has lost {streak} trades in a row on {symbol} "
              f"during {market_state} markets in the {session} session -- new entries matching "
              f"this exact pattern are paused until a person reviews it.")
    storage.save_paper_auto_avoid_rule(
        strategy_id, strategy_name, symbol, market_state, session, streak, reason, _now_iso(),
    )
    return reason


def is_avoided(strategy_id, symbol, market_state, session):
    """Checked by the engine before opening a new position -- returns the
    veto reason string if this exact pattern is currently avoided, else
    None. A pattern with no rule (or a deactivated one) is never avoided --
    the absence of an active row IS "not avoided", so a brand-new pattern
    with zero history degrades gracefully to "allowed"."""
    if not strategy_id or not symbol or not market_state or not session:
        return None
    return storage.is_pattern_auto_avoided(strategy_id, symbol, market_state, session)
