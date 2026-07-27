"""Drawdown Protection Engine (Risk & Safety Group, item 4): upgrades the
existing Drawdown Alert (informational-only, see insights.detect_alerts)
into an actual protection mechanism. When a strategy's OWN losing streak or
OWN drawdown-from-peak crosses a configured threshold
(paper_trading.config's drawdown_pause_streak_threshold /
drawdown_pause_pct_threshold), that ONE strategy is paused from opening new
Paper Trading positions -- existing open positions keep being monitored and
closed normally by position_manager.monitor_and_close(), which never checks
the pause flag. This is deliberately strategy-scoped, never system-wide:
one strategy pausing has no effect on any other strategy's book.

Reversible: storage.set_strategy_paused(strategy_id, False, ...) (wired to
a "Resume Strategy" dashboard button) clears the pause immediately."""

from datetime import datetime, timezone

from data_engine import storage
from paper_trading import config as pt_config
from paper_trading import insights


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def evaluate_strategy(strategy_id, strategy_name):
    """Re-checks this strategy's own streak + drawdown after a trade close
    and pauses it if either configured threshold is crossed. Returns the
    pause reason if a pause was (newly) applied this call, else None.
    Degrades gracefully: insights.compute_streak/compute_risk_metrics both
    already return safe empty/None values for a strategy with too little
    history, so a brand-new strategy is never falsely paused."""
    if not strategy_id:
        return None

    already_paused, _, _ = storage.is_strategy_paused(strategy_id)
    if already_paused:
        # Strategy Graveyard (Confidence & Signal Quality Group, item 9):
        # burial only applies once a strategy is ALREADY paused and its
        # streak keeps growing past the (stricter) burial bar -- checked
        # here since this is the one place that already re-evaluates the
        # streak on every trade close, paused or not.
        from paper_trading import graveyard
        graveyard.bury_if_abandoned(strategy_id, strategy_name)
        return None  # don't re-trigger/overwrite an existing pause's reason

    settings = pt_config.load()
    streak_threshold = settings.get("drawdown_pause_streak_threshold", 7)
    pct_threshold = settings.get("drawdown_pause_pct_threshold", 15.0)

    streak = insights.compute_streak(strategy_id)
    if streak["type"] == "loss" and streak["count"] >= streak_threshold:
        reason = (f"{streak['count']} consecutive losses (threshold: {streak_threshold}). "
                   f"New trades paused for this strategy; existing open positions are unaffected.")
        storage.set_strategy_paused(strategy_id, True, reason, _now_iso())
        return reason

    metrics = insights.compute_risk_metrics(strategy_id, since=insights.fresh_session_start())
    current_dd = metrics.get("current_drawdown_pct")
    if current_dd is not None and current_dd >= pct_threshold:
        reason = (f"drawdown reached {current_dd:.1f}% from this strategy's peak balance "
                   f"(threshold: {pct_threshold:.0f}%). New trades paused; existing open "
                   f"positions are unaffected.")
        storage.set_strategy_paused(strategy_id, True, reason, _now_iso())
        return reason

    return None


def resume_strategy(strategy_id):
    """Reverses a pause -- called from the dashboard's "Resume Strategy"
    button. Always safe to call even if the strategy wasn't paused."""
    storage.set_strategy_paused(strategy_id, False, None, _now_iso())
