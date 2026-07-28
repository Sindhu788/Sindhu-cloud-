"""Pattern-Based Auto-Avoid Rule (Self-Learning Group, item 1; strengthened
to a statistical gate in the Genuine Evolution Engine pass): when one
EXACT pattern -- a specific (strategy, symbol, market_state, session)
combination -- has a full trade history that is STATISTICALLY reliable
(see paper_trading.pattern_stats -- Wilson score interval, minimum 25
trades) and confidently one-sided toward losing, new entries matching
that exact pattern are suppressed going forward. This never touches the
strategy itself (it keeps trading every OTHER coin/market condition
normally) and never deletes anything -- it's a reversible, fully-logged
veto recorded in paper_auto_avoid_rules.

Previously this triggered off 5 CONSECUTIVE losses, which can plausibly
happen by chance alone (about 1 in 32 times at a true 50/50 coin flip,
and easily reachable within a strategy's first dozen trades on a coin).
It now requires the full pattern's win/loss record to clear
pattern_stats.MIN_SAMPLE_SIZE (25 trades) AND for the Wilson 95%
confidence interval's upper bound to sit below pattern_stats.BAD_UPPER_BOUND
(45%) -- i.e. statistically confident the pattern's TRUE win rate is
below 45%, not just an unlucky short run.

Called after every trade close (see paper_trading.position_manager) --
cheap (one indexed query over one pattern's own trades, not a full scan)."""

from datetime import datetime, timezone

from data_engine import storage
from paper_trading import pattern_stats


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def evaluate_pattern(strategy_id, strategy_name, symbol, market_state, session, since=None):
    """Recomputes this exact pattern's full win/loss record and, once it's
    statistically reliable (pattern_stats.classify), creates/refreshes the
    auto-avoid rule if the pattern is confidently a loser -- or deactivates
    an existing rule if the pattern has since recovered to no longer be a
    confident loser (a real person can always see why via the `reason`
    text, which always states the current sample size and confidence
    interval). Returns the rule reason string if a rule was (re)triggered
    this call, else None."""
    if not strategy_id or not symbol or not market_state or not session:
        return None  # degrade gracefully -- a lesson-only trade has no strategy_id to scope a rule to

    trades = storage.list_paper_pattern_trades_ordered(strategy_id, symbol, market_state, session, since=since)
    n = len(trades)
    wins = sum(1 for t in trades if t["pnl"] is not None and t["pnl"] > 0)
    result = pattern_stats.classify(wins, n)

    if result["status"] != "reliable_bad":
        # Not (or no longer) a statistically confident loser -- if a rule
        # exists from an earlier, now-stale read, deactivate it rather than
        # leaving a strategy permanently blocked on evidence that no longer holds.
        existing = storage.is_pattern_auto_avoided(strategy_id, symbol, market_state, session)
        if existing:
            for rule in storage.list_paper_auto_avoid_rules(active_only=True):
                if (rule["strategy_id"] == strategy_id and rule["symbol"] == symbol
                        and rule["market_state"] == market_state and rule["session"] == session):
                    storage.deactivate_paper_auto_avoid_rule(rule["id"], _now_iso())
        return None

    reason = (
        f"{strategy_name or strategy_id} on {symbol} during {market_state} markets in the "
        f"{session} session has a {result['win_rate_pct']:.0f}% win rate over {n} trades "
        f"(95% confidence interval: {result['ci_lower_pct']:.0f}%-{result['ci_upper_pct']:.0f}%) -- "
        f"statistically confident this pattern loses more than it wins. New entries matching this "
        f"exact pattern are paused until a person reviews it."
    )
    storage.save_paper_auto_avoid_rule(
        strategy_id, strategy_name, symbol, market_state, session, n, reason, _now_iso(),
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
