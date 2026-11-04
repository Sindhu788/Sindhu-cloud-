"""Exact resampling of 1-minute candles to higher timeframes (numpy only).

Rules (Step 11): open = first open, high = max high, low = min low, close = last close, volume / quote_volume / trades / taker volumes = sum.
A window is built ONLY if ALL of its 1-minute candles are present; incomplete windows are dropped (never filled, never partially built).
Boundaries: windows are aligned to UTC epoch multiples of the timeframe: 3m/5m/15m/30m/1h/2h/4h/6h/12h start at UTC multiples of the
period from 00:00; 1d starts at 00:00 UTC; 1w starts on Monday 00:00 UTC (Binance's documented weekly candle opens on Monday 00:00 UTC;
epoch day 0 (1970-01-01) was a Thursday, so the weekly offset is 4 days). Binance daily candles are UTC (documented: kline intervals are
UTC unless a timeZone parameter is passed). There is NO 1-month timeframe (only 12 bars per year).
"""
import numpy as np

MINUTE_MS = 60_000
TIMEFRAMES_MIN = {"3m": 3, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "2h": 120, "4h": 240, "6h": 360, "12h": 720, "1d": 1440, "1w": 10080}
WEEK_OFFSET_MIN = 4 * 1440      # 1970-01-01 was a Thursday: Monday-aligned weeks start 4 days after the epoch multiple


def window_start(open_time_ms, tf):
    p = TIMEFRAMES_MIN[tf] * MINUTE_MS
    off = WEEK_OFFSET_MIN * MINUTE_MS if tf == "1w" else 0
    return ((open_time_ms - off) // p) * p + off


def resample(a, tf):
    """a: dict of numpy arrays from store.to_arrays (sorted, unique 1m candles). Returns a dict of arrays for `tf` with complete windows only."""
    if tf not in TIMEFRAMES_MIN:
        raise ValueError(f"unsupported timeframe {tf!r} (no 1-month timeframe by design)")
    k = TIMEFRAMES_MIN[tf]
    ot = a["open_time"]
    if len(ot) == 0:
        return {n: v[:0] for n, v in a.items()}
    ws = window_start(ot, tf)
    # group boundaries: indices where the window start changes
    change = np.empty(len(ot), bool)
    change[0] = True
    change[1:] = ws[1:] != ws[:-1]
    idx = np.flatnonzero(change)
    ends = np.append(idx[1:], len(ot))
    counts = ends - idx
    # a window is complete when it holds exactly k candles AND they are consecutive minutes
    span_ok = (ot[ends - 1] - ot[idx]) == (k - 1) * MINUTE_MS
    keep = (counts == k) & span_ok
    idx, ends = idx[keep], ends[keep]
    out = {"open_time": ws[idx]}
    out["open"] = a["open"][idx]
    out["close"] = a["close"][ends - 1]
    out["high"] = np.maximum.reduceat(a["high"], np.flatnonzero(change))[keep]
    out["low"] = np.minimum.reduceat(a["low"], np.flatnonzero(change))[keep]
    for n in ("volume", "quote_volume", "taker_buy_base", "taker_buy_quote"):
        out[n] = np.add.reduceat(a[n], np.flatnonzero(change))[keep]
    out["trades"] = np.add.reduceat(a["trades"].astype("int64"), np.flatnonzero(change))[keep]
    return out
