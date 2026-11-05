"""Prepared signal rules (Day 6 Step 17). BOTH ARE OFF BY DEFAULT: with no environment variable set nothing here ever blocks a signal.
Both are owner decisions (docs/OWNER_DECISIONS.md); they are wired into paper_trading.telegram_bot.send_signal_for_position next to the existing
duplicate / congestion checks and only ever WITHHOLD a Telegram message (the paper trade itself is untouched).

(a) Opposite-direction block. SINDHU_BLOCK_OPPOSITE_SIGNAL=1 turns it on. A signal is withheld when a signal in the OPPOSITE direction on the same coin
    was successfully sent within the last SINDHU_OPPOSITE_SIGNAL_WINDOW_MIN minutes (default 30).
(b) Target-to-stop cap. SINDHU_MAX_TARGET_STOP_RATIO=<number> turns it on (for example 5). A signal is withheld when
    |take_profit - entry| / |entry - stop_loss| is larger than the number - a target 9.6-9.9 times the stop cannot be reached in "a few hours to 1 day".
"""
import os
from datetime import datetime, timedelta, timezone

DEFAULT_OPPOSITE_WINDOW_MIN = 30


def _truthy(v):
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def opposite_window_minutes(env=None):
    """None when the rule is OFF, else the window in minutes."""
    env = os.environ if env is None else env
    if not _truthy(env.get("SINDHU_BLOCK_OPPOSITE_SIGNAL")):
        return None
    try:
        m = int(float(env.get("SINDHU_OPPOSITE_SIGNAL_WINDOW_MIN", DEFAULT_OPPOSITE_WINDOW_MIN)))
    except (TypeError, ValueError):
        m = DEFAULT_OPPOSITE_WINDOW_MIN
    return m if m > 0 else DEFAULT_OPPOSITE_WINDOW_MIN


def max_target_stop_ratio(env=None):
    """None when the rule is OFF (unset, empty, zero, negative or not a number)."""
    env = os.environ if env is None else env
    try:
        r = float(env.get("SINDHU_MAX_TARGET_STOP_RATIO", ""))
    except (TypeError, ValueError):
        return None
    return r if r > 0 else None


def target_stop_ratio(position):
    try:
        e, sl, tp = float(position["entry_price"]), float(position["stop_loss"]), float(position["take_profit"])
    except (KeyError, TypeError, ValueError):
        return None
    risk = abs(e - sl)
    return abs(tp - e) / risk if risk > 0 else None


def check_target_stop_cap(position, env=None):
    cap = max_target_stop_ratio(env)
    if cap is None:
        return True, None
    ratio = target_stop_ratio(position)
    if ratio is not None and ratio > cap:
        return False, (f"take-profit is {ratio:.1f} times the stop distance (limit {cap:g}) - too far to be realistic for the stated duration; withheld")
    return True, None


def check_opposite_direction(position, lookup, now=None, env=None):
    """lookup(symbol, opposite_direction, since_iso) -> name of a strategy that already sent an opposite signal in the window, or None."""
    minutes = opposite_window_minutes(env)
    if minutes is None:
        return True, None
    symbol, direction = position.get("symbol"), str(position.get("direction") or "").lower()
    if not symbol or direction not in ("long", "short"):
        return True, None
    opposite = "short" if direction == "long" else "long"
    now = now or datetime.now(timezone.utc)
    since_iso = (now - timedelta(minutes=minutes)).isoformat()
    other = lookup(symbol, opposite, since_iso)
    if other:
        return False, (f"{other} already sent a {opposite} signal for {symbol} within the last {minutes} minutes - a {direction} signal now would "
                       f"contradict it; withheld")
    return True, None
