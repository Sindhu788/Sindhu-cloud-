"""Master Task 6, 2.3 -- optional, per-strategy HTF (Higher Timeframe)
Confluence Filter: before a signal is finalized, checks that a higher
timeframe's structural trend agrees with the signal's own direction,
suppressing the signal when it doesn't.

Reuses backtest_engine.concepts.valid_structure_trend() -- the project's
one existing structural-trend state machine (a swing low/high is only
considered to have flipped the trend once a specific prior swing high/low
is genuinely broken, not on every minor wiggle) -- no new trend-detection
mechanism is built here.

OFF by default, opt-in per strategy via paper_strategy_config.
htf_confluence_filter_enabled -- see data_engine.storage.
get_paper_strategy_config()/set_strategy_signal_filter_overrides(). An
existing strategy's behavior never changes unless this is explicitly
turned on for it.
"""

import time

from backtest_engine import concepts
from data_engine.resample import get_ohlcv

# One level (or two, matching the task's own "15m entry -> check 1h AND
# 4h" example) above each entry timeframe. Deliberately a small, explicit
# table rather than a generic "next N buckets" computation -- easy to
# read, easy to audit, and covers every timeframe an actual strategy in
# this project uses (see SUPPORTED_INTERVALS in data_engine/config.py).
_HTF_MAP = {
    "1m": ["15m", "1h"], "3m": ["15m", "1h"], "5m": ["1h", "4h"],
    "15m": ["1h", "4h"], "30m": ["4h", "1d"], "1h": ["4h", "1d"],
    "2h": ["4h", "1d"], "4h": ["1d"], "6h": ["1d"], "12h": ["1d"],
    "1d": ["1w"], "1w": [],
}

# Enough history for valid_structure_trend()'s swing-point state machine to
# have settled on a real trend by the most recent bar, per timeframe.
_LOOKBACK_MS = {
    "15m": 30 * 24 * 3600 * 1000, "1h": 90 * 24 * 3600 * 1000,
    "4h": 180 * 24 * 3600 * 1000, "1d": 365 * 24 * 3600 * 1000,
    "1w": 3 * 365 * 24 * 3600 * 1000,
}
_DEFAULT_LOOKBACK_MS = 90 * 24 * 3600 * 1000
_MIN_BARS = 10


def _now_ms():
    return int(time.time() * 1000)


def higher_timeframes_for(entry_timeframe):
    return _HTF_MAP.get(entry_timeframe, [])


def htf_trend(exchange, symbol, htf_timeframe):
    """Latest valid_structure_trend() value on one higher timeframe:
    "up", "down", or None. None covers both "not enough data yet" and
    "no valid swing has broken a prior one yet" -- treated identically by
    check() below (never a contradiction, only an active opposite trend
    is)."""
    end_ms = _now_ms()
    start_ms = end_ms - _LOOKBACK_MS.get(htf_timeframe, _DEFAULT_LOOKBACK_MS)
    df = get_ohlcv(exchange, symbol, interval=htf_timeframe, start_ms=start_ms, end_ms=end_ms)
    if df is None or len(df) < _MIN_BARS:
        return None
    trend = concepts.valid_structure_trend(df)
    last = trend.iloc[-1]
    return last if last in ("up", "down") else None


def check(exchange, symbol, entry_timeframe, direction):
    """direction is the candidate's own "bullish"/"bearish" vocabulary.

    Returns (allowed: bool, reason: str | None). Only ever blocks on an
    ACTIVE contradiction from an established HTF trend -- an entry
    timeframe with no configured HTF, or an HTF with no settled trend yet,
    always allows the signal through. This is deliberately conservative in
    the other direction too: ANY checked HTF contradicting is enough to
    suppress, since the whole point is not fighting a higher timeframe."""
    wanted = "up" if direction == "bullish" else "down"
    for htf in higher_timeframes_for(entry_timeframe):
        trend = htf_trend(exchange, symbol, htf)
        if trend is not None and trend != wanted:
            return False, f"HTF confluence filter: {htf} structural trend is {trend}, contradicts this {direction} signal"
    return True, None
