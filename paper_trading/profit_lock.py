"""Profit-Lock Trailing Stop (Grand Feature Expansion, Phase 5 Feature 9):
once a position has moved favorably by at least `trigger_r` times its own
original risk (entry-to-stop distance), the stop-loss trails behind the
position's best price seen so far to lock in `trail_pct` of that favorable
move. Confirmed absent at both the per-position level (position_manager.py
only ever checked a fixed stop_loss/take_profit, no trailing/breakeven
logic) and the portfolio level (account_drawdown_guard.py is a downside-
only circuit breaker) before this was built.

Reuses Phase 3's highest_price_seen/lowest_price_seen excursion tracking
(MAE/MFE) as the "best price so far" input -- no new tracking mechanism.
The computed stop is only ever a TIGHTENING; the caller (position_manager.
monitor_and_close) is responsible for never applying a value that would
loosen the existing stop-loss, which compute_trailing_stop already
guarantees by returning None whenever it wouldn't be an improvement."""


def compute_trailing_stop(direction, entry_price, original_stop_loss, highest_price_seen,
                           lowest_price_seen, trigger_r=1.0, trail_pct=50.0):
    """Returns a new, tighter stop-loss price, or None if the trail hasn't
    triggered yet (or wouldn't improve on the current stop)."""
    if original_stop_loss is None or entry_price is None:
        return None
    risk_per_unit = abs(entry_price - original_stop_loss)
    if risk_per_unit <= 0:
        return None

    if direction == "long":
        if highest_price_seen is None:
            return None
        favorable_move = highest_price_seen - entry_price
        if favorable_move < trigger_r * risk_per_unit:
            return None
        new_stop = entry_price + favorable_move * (trail_pct / 100.0)
        return new_stop if new_stop > original_stop_loss else None
    else:
        if lowest_price_seen is None:
            return None
        favorable_move = entry_price - lowest_price_seen
        if favorable_move < trigger_r * risk_per_unit:
            return None
        new_stop = entry_price - favorable_move * (trail_pct / 100.0)
        return new_stop if new_stop < original_stop_loss else None
