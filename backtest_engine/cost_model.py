"""Real transaction-cost figures for this platform, used to sanity-check a
buffer-based stop-loss BEFORE a strategy is finalized -- see the CRT 2.0
rebuild batch, where a 0.15% buffer turned out to be smaller than the real
round-trip transaction cost, causing near-100% drawdown on an otherwise
correctly-built strategy (stops got hit by commission+slippage noise alone,
regardless of trade direction).

REAL_COMMISSION_PCT/REAL_SLIPPAGE_PCT mirror sindhu_web/api/backtesting.py's
RunRequest defaults (commission_pct=0.1, slippage_pct=0.05) -- the actual
values a real backtest run through the live app uses. backtest_engine
deliberately does not import sindhu_web (that would create a circular /
wrong-direction dependency, since sindhu_web imports backtest_engine, not
the other way around), so these are a documented mirror: update BOTH places
if the platform's real default transaction costs ever change.

Standalone, read-only utility -- not wired into engine.py's execution path
or any existing strategy. Call check_buffer_safety() while CONSTRUCTING a
new strategy's stop-loss, before saving/backtesting it.
"""

REAL_COMMISSION_PCT = 0.1
REAL_SLIPPAGE_PCT = 0.05


def real_round_trip_cost_pct(commission_pct=None, slippage_pct=None):
    """Round-trip transaction cost as a percentage of price: commission +
    slippage, each charged once on entry AND once on exit. Defaults to the
    platform's real configured values (see module docstring); pass explicit
    values only if a strategy is deliberately using non-default settings."""
    c = REAL_COMMISSION_PCT if commission_pct is None else commission_pct
    s = REAL_SLIPPAGE_PCT if slippage_pct is None else slippage_pct
    return round(2 * (c + s), 10)  # avoid float noise like 0.30000000000000004


def check_buffer_safety(buffer_pct, min_multiple=2.0, commission_pct=None, slippage_pct=None):
    """Checks a chosen stop-loss buffer (in %) against the real round-trip
    transaction cost. Returns a dict:
      is_safe            -- bool
      round_trip_cost_pct -- the real cost this was checked against
      required_min_pct    -- min_multiple * round_trip_cost_pct
      warning              -- human-readable string if unsafe, else None

    Warns (does not raise/block) if buffer_pct < min_multiple * real
    round-trip cost -- e.g. CRT 2.0's original 0.15% buffer against a 0.30%
    round-trip cost is only 0.5x, nowhere near the recommended 2x floor."""
    cost = real_round_trip_cost_pct(commission_pct, slippage_pct)
    required = round(min_multiple * cost, 10)
    is_safe = buffer_pct >= required
    warning = None
    if not is_safe:
        warning = (
            f"Stop-loss buffer {buffer_pct}% is less than {min_multiple}x the real round-trip "
            f"transaction cost ({cost}%, required minimum {required}%). Stops may get hit by "
            f"commission+slippage noise alone, regardless of trade direction -- raise the buffer "
            f"before finalizing this strategy."
        )
    return {
        "is_safe": is_safe,
        "round_trip_cost_pct": cost,
        "required_min_pct": required,
        "warning": warning,
    }
