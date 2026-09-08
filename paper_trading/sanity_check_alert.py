"""Grand Master Prompt, Phase 5: Sanity Check Alert -- a live,
informational check on each newly-opened paper position for basic red-
flag conditions (implausible risk sizing, implausible stop distance, a
non-positive size). NEVER blocks a trade -- this only ever runs AFTER
position_manager.open_position() has already succeeded, purely to flag a
signal worth a second look. Distinct from backtest_engine/sanity_check.py
(a pre-backtest strategy-config plausibility check, not a live-signal
check) -- confirmed nothing equivalent existed for live signals/trades.

Same throttle-free "just log an alert" shape as paper_trading/insights.py's
sweep_win_rate_decay_alerts, reusing the existing paper_alerts table so
this needs no new notification channel.
"""
from datetime import datetime, timezone

from data_engine import storage

MAX_SANE_RISK_PCT_OF_BALANCE = 0.10   # 10% of one book's own balance in a single trade
MIN_SANE_STOP_DISTANCE_PCT = 0.05     # a stop within 0.05% of entry is almost certainly a data/config glitch
MAX_SANE_STOP_DISTANCE_PCT = 50.0     # a stop 50%+ away from entry is almost certainly a data/config glitch


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def check_position(position, book_balance):
    """Pure function, no I/O -- returns a list of red-flag reason strings
    (empty if nothing looks wrong)."""
    reasons = []
    entry = position.get("entry_price")
    stop = position.get("stop_loss")
    risk_amount = position.get("risk_amount")

    if risk_amount is not None and book_balance:
        risk_pct = risk_amount / book_balance
        if risk_pct > MAX_SANE_RISK_PCT_OF_BALANCE:
            reasons.append(f"risk_amount ({risk_amount:.2f}) is {risk_pct:.1%} of this book's balance "
                            f"-- unusually large for one trade")

    if entry and stop:
        stop_distance_pct = abs(entry - stop) / entry * 100
        if stop_distance_pct < MIN_SANE_STOP_DISTANCE_PCT:
            reasons.append(f"stop-loss is only {stop_distance_pct:.3f}% from entry -- suspiciously tight")
        elif stop_distance_pct > MAX_SANE_STOP_DISTANCE_PCT:
            reasons.append(f"stop-loss is {stop_distance_pct:.1f}% from entry -- suspiciously wide")

    if position.get("size") is not None and position["size"] <= 0:
        reasons.append("position size is zero or negative")

    return reasons


def check_and_alert(position, book_key, strategy_name, book_balance):
    """Returns the alert message if a red flag was raised, else None.
    Writes to the existing paper_alerts table -- never raises, never
    modifies the position or blocks anything (the trade this checks has
    already been opened by the time this runs)."""
    reasons = check_position(position, book_balance)
    if not reasons:
        return None
    message = (f"{strategy_name or book_key or 'lesson-only'}: {position['symbol']} signal flagged -- "
               f"{'; '.join(reasons)}. The trade was still opened normally -- this is informational only.")
    storage.create_paper_alert("sanity_check", book_key, strategy_name, message, "warning", _now_iso())
    return message
