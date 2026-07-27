"""Stress Testing Engine, basic version (Additional Features, B5): finds
the single worst (most extreme price-movement) week already present in a
symbol's REAL stored history, then re-runs the strategy specifically
against that window -- not a synthetic crash simulation, just replaying
the worst real period that actually happened.

Reuses automation_pipeline.optimizer._run_in_memory (the exact same
in-memory, no-DB-write backtest execution Walk-Forward Testing already
uses for its own sub-window scoring) -- the backtest engine itself is
never modified or reimplemented, only pointed at a different date range.
"""

from data_engine import storage
from data_engine.resample import get_ohlcv
from automation_pipeline import optimizer
from backtest_engine import strategy_library as lib

_WEEK_MS = 7 * 24 * 3600 * 1000
_MIN_HOURLY_BARS_PER_WEEK = 20  # degrade gracefully on a too-short/gappy window


def find_worst_week(exchange, symbol):
    """Scans the symbol's FULL stored 1h history in non-overlapping
    7-day windows and returns the one with the largest high-to-low price
    range as a % of that week's starting price -- the plainest, most
    defensible definition of "most extreme volatility week" from data
    already on disk. Returns None if there's under one week of history."""
    min_ms, max_ms = storage.get_symbol_time_bounds(exchange, symbol)
    if min_ms is None or max_ms is None or max_ms - min_ms < _WEEK_MS:
        return None

    worst = None
    start = min_ms
    while start < max_ms:
        end = min(start + _WEEK_MS, max_ms)
        df = get_ohlcv(exchange, symbol, interval="1h", start_ms=start, end_ms=end)
        if len(df) >= _MIN_HOURLY_BARS_PER_WEEK:
            start_price = float(df["close"].iloc[0])
            if start_price > 0:
                range_pct = round((float(df["high"].max()) - float(df["low"].min())) / start_price * 100, 2)
                if worst is None or range_pct > worst["range_pct"]:
                    worst = {"start_ms": start, "end_ms": end, "range_pct": range_pct}
        start += _WEEK_MS
    return worst


def run_stress_test(strategy_id, exchange, symbol, initial_balance=10000.0):
    """Returns {"available": False, "reason": ...} when there isn't enough
    history or the strategy never traded in that window (degrades
    gracefully rather than reporting a misleading empty result as a
    pass)."""
    try:
        cfg = lib.load(strategy_id)
    except Exception as e:
        return {"available": False, "reason": f"could not load strategy: {e!r}"}

    worst_week = find_worst_week(exchange, symbol)
    if worst_week is None:
        return {"available": False, "reason": f"not enough stored history for {symbol} to find a worst week"}

    settings = {"initial_balance": initial_balance}
    metrics = optimizer._run_in_memory(cfg, exchange, symbol, settings, worst_week["start_ms"], worst_week["end_ms"])
    if metrics is None or metrics.get("total_trades", 0) == 0:
        return {
            "available": False,
            "reason": "strategy generated no trades during its worst historical week -- nothing to stress-test",
            "worst_week": worst_week,
        }

    return {"available": True, "strategy_id": strategy_id, "symbol": symbol, "worst_week": worst_week, "metrics": metrics}
