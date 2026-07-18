"""Vectorized implementations of the indicators/concepts a strategy can
reference. Every function is causal -- it never uses information that
would not actually be known yet at the bar where it's read. Structural
concepts (BOS/CHoCH/Order Block/Breaker Block) are confirmed only a few
bars after the pivot they describe, exactly like a human reading the chart
would need those bars to close first before calling it a swing point.
"""

import numpy as np
import pandas as pd


# ------------------------------------------------------------ indicators

def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


def sma(series, period):
    return series.rolling(period).mean()


def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    value = 100 - (100 / (1 + rs))
    return value.fillna(50.0)


def macd(series, fast=12, slow=26, signal=9):
    macd_line = ema(series, fast) - ema(series, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def atr(df, period=14):
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def vwap_daily(df):
    """VWAP reset at each UTC day boundary (the standard convention)."""
    typical = (df["high"] + df["low"] + df["close"]) / 3
    pv = typical * df["volume"]
    day_key = pd.Series(df.index.date, index=df.index)
    cum_pv = pv.groupby(day_key).cumsum()
    cum_vol = df["volume"].groupby(day_key).cumsum()
    return cum_pv / cum_vol.replace(0, np.nan)


def volume_filter(df, period=20, multiplier=1.5):
    avg_vol = df["volume"].rolling(period).mean()
    return (df["volume"] > (avg_vol * multiplier)).fillna(False)


def trend_filter(df, period=50):
    """"up"/"down" based on close vs. its EMA -- a simple, transparent trend
    filter a strategy can gate entries on."""
    ma = ema(df["close"], period)
    return pd.Series(np.where(df["close"] > ma, "up", "down"), index=df.index)


# ------------------------------------------------------------ session tagging

_SESSION_WINDOWS_UTC = [
    ("asian", 0, 8),
    ("london", 8, 13),
    ("ny", 13, 21),
]


def session_of_hour(hour):
    for name, start, end in _SESSION_WINDOWS_UTC:
        if start <= hour < end:
            return name
    return "off_hours"


def session_column(df):
    """Approximate trading session per bar from its UTC hour. Real session
    boundaries shift a little with DST; this fixed-hour approximation is
    good enough for session-performance comparison. Vectorized (np.select
    over the same _SESSION_WINDOWS_UTC ranges) instead of a per-row Python
    loop -- verified byte-for-byte identical to the old row-by-row version
    across multiple symbols/timeframes."""
    hours = df.index.hour.values
    conditions = [(hours >= start) & (hours < end) for _, start, end in _SESSION_WINDOWS_UTC]
    choices = [name for name, _, _ in _SESSION_WINDOWS_UTC]
    return pd.Series(np.select(conditions, choices, default="off_hours"), index=df.index)


# ------------------------------------------------------------ structure (ICT/SMC)

def swing_points(df, lookback=2):
    """Boolean series marking confirmed swing highs/lows. A swing point at
    the true pivot bar is only marked True `lookback` bars later, once the
    bars on both sides that confirm it have actually closed."""
    window = lookback * 2 + 1
    high, low = df["high"], df["low"]

    is_high = high == high.rolling(window, center=True).max()
    is_low = low == low.rolling(window, center=True).min()

    swing_high = is_high.shift(lookback).fillna(False).astype(bool)
    swing_low = is_low.shift(lookback).fillna(False).astype(bool)
    return swing_high, swing_low


def support_resistance(df, lookback=2):
    swing_high, swing_low = swing_points(df, lookback)
    resistance = df["high"].where(swing_high).ffill()
    support = df["low"].where(swing_low).ffill()
    return support, resistance


def break_of_structure(df, lookback=2):
    """Bullish BOS: close breaks above the most recently confirmed swing
    high (trend continuation up). Bearish BOS: the mirror case down."""
    swing_high, swing_low = swing_points(df, lookback)
    swing_high_level = df["high"].where(swing_high).ffill()
    swing_low_level = df["low"].where(swing_low).ffill()

    bullish_bos = (df["close"] > swing_high_level).fillna(False)
    bearish_bos = (df["close"] < swing_low_level).fillna(False)
    return bullish_bos, bearish_bos


def change_of_character(df, lookback=2):
    """CHoCH: a BOS in the opposite direction of the currently established
    trend -- the first sign a trend may be reversing. Vectorized (the
    per-bar "current trend" state is just the last non-null BOS direction
    forward-filled) instead of a per-bar Python loop -- verified
    byte-for-byte identical to the old row-by-row version across multiple
    symbols/timeframes."""
    bullish_bos, bearish_bos = break_of_structure(df, lookback)
    up, down = bullish_bos.values, bearish_bos.values

    trend_raw = pd.Series(np.where(up, "up", np.where(down, "down", None)), index=df.index)
    trend_s = trend_raw.ffill().shift(1)
    bullish_choch = (bullish_bos & (trend_s == "down")).fillna(False)
    bearish_choch = (bearish_bos & (trend_s == "up")).fillna(False)
    return bullish_choch, bearish_choch


def fair_value_gap(df):
    """3-candle imbalance: a gap left between candle i-2 and candle i that
    price hasn't traded through yet."""
    bullish_fvg = (df["low"] > df["high"].shift(2)).fillna(False)
    bearish_fvg = (df["high"] < df["low"].shift(2)).fillna(False)
    return bullish_fvg, bearish_fvg


def order_blocks(df, lookback=2):
    """The last opposite-direction candle before a BOS -- the zone
    considered "smart money" footprint before the impulsive move.
    Returns four series: bullish_ob_low/high, bearish_ob_low/high, each
    holding the currently active order block's price range as of that bar
    (None until one has actually been confirmed by a BOS). Vectorized (each
    "active zone" is the most recent qualifying candle's low/high,
    forward-filled) instead of a per-bar Python loop -- verified
    byte-for-byte identical to the old row-by-row version across multiple
    symbols/timeframes."""
    bullish_bos, bearish_bos = break_of_structure(df, lookback)
    bearish_candle = df["close"] < df["open"]
    bullish_candle = df["close"] > df["open"]

    last_bearish_low = df["low"].where(bearish_candle).ffill()
    last_bearish_high = df["high"].where(bearish_candle).ffill()
    last_bullish_low = df["low"].where(bullish_candle).ffill()
    last_bullish_high = df["high"].where(bullish_candle).ffill()

    bull_low = last_bearish_low.where(bullish_bos).ffill()
    bull_high = last_bearish_high.where(bullish_bos).ffill()
    bear_low = last_bullish_low.where(bearish_bos).ffill()
    bear_high = last_bullish_high.where(bearish_bos).ffill()
    return bull_low, bull_high, bear_low, bear_high


def liquidity_sweep(df, lookback=2):
    """Generic liquidity sweep / stop hunt: price wicks beyond the most
    recently confirmed swing support/resistance level then closes back on
    the other side -- anchored to swing structure rather than a specific
    fixed level (see pdh_pdl_sweep() for the PDH/PDL-anchored variant)."""
    support, resistance = support_resistance(df, lookback)
    low, high, close = df["low"], df["high"], df["close"]
    bullish_sweep = ((low < support) & (close > support)).fillna(False)
    bearish_sweep = ((high > resistance) & (close < resistance)).fillna(False)
    return bullish_sweep, bearish_sweep


def candle_break(df):
    """"Trigger candle" pattern: a bullish (green) candle forms, then a
    LATER candle trades above that candle's high -> bullish break; a
    bearish (red) candle forms, then a later candle trades below its low ->
    bearish break.

    Added because this is extremely common phrasing in real strategy
    documents ("wait for a green candle, enter when its high is broken")
    but had no executable equivalent, so AI extraction was forced to emit
    type="raw" for it -- an unexecutable condition that silently produces
    zero trades. Mapping it onto the existing `trend` condition instead
    would have been wrong: trend_filter() is an EMA-slope reading, not
    candle colour, so "red candle" and "bearish trend" are different facts.

    Causal by construction: the reference high/low is shifted one bar
    before comparison, so a candle can never trigger a break of itself and
    nothing reads a value that wasn't already closed."""
    bullish = df["close"] > df["open"]
    bearish = df["close"] < df["open"]
    # Most recent bullish/bearish candle's extreme, as known BEFORE this bar.
    last_bull_high = df["high"].where(bullish).ffill().shift(1)
    last_bear_low = df["low"].where(bearish).ffill().shift(1)
    bull_break = (df["high"] > last_bull_high).fillna(False)
    bear_break = (df["low"] < last_bear_low).fillna(False)
    return bull_break, bear_break


def previous_day_high_low(df):
    """Previous UTC day's high/low, available for every bar of the CURRENT
    day -- yesterday is fully closed by midnight UTC, so this is causal:
    today's PDH/PDL never reflects anything not yet known when it's read."""
    day_key = pd.Series(df.index.date, index=df.index)
    daily_high = df["high"].groupby(day_key).max()
    daily_low = df["low"].groupby(day_key).min()
    pdh = day_key.map(daily_high.shift(1))
    pdl = day_key.map(daily_low.shift(1))
    return pdh, pdl


def pdh_pdl_sweep(df):
    """Classic liquidity-grab pattern anchored to the previous day's
    high/low: price dips below PDL then closes back above it (bullish
    sweep/grab), or spikes above PDH then closes back below it (bearish)."""
    pdh, pdl = previous_day_high_low(df)
    low, high, close = df["low"], df["high"], df["close"]
    pdl_sweep = ((low < pdl) & (close > pdl)).fillna(False)
    pdh_sweep = ((high > pdh) & (close < pdh)).fillna(False)
    return pdl_sweep, pdh_sweep


def fvg_zone(df):
    """Active Fair Value Gap zone bounds (low/high), tracked the same way
    order_blocks()/breaker_blocks() track their active zone -- lets a
    strategy use "SL below the FVG" as a real price anchor instead of only
    a boolean flag. Does not change fair_value_gap()'s own return shape
    (still just the two boolean series) so every existing caller of it is
    unaffected; this is an additional, separate function. Vectorized
    (shift+where+ffill) instead of a per-bar Python loop -- verified
    byte-for-byte identical to the old row-by-row version across multiple
    symbols/timeframes. NOTE: bull_low/bull_high and bear_low/bear_high
    preserve the original tuple order exactly (active_bull=(high[i-2],
    low[i]), active_bear=(high[i], low[i-2])) even though the naming looks
    swapped -- that's the pre-existing behavior, not something to "fix"."""
    bullish_fvg, bearish_fvg = fair_value_gap(df)
    low, high = df["low"], df["high"]

    bull_low = high.shift(2).where(bullish_fvg).ffill()
    bull_high = low.where(bullish_fvg).ffill()
    bear_low = high.where(bearish_fvg).ffill()
    bear_high = low.shift(2).where(bearish_fvg).ffill()
    return bull_low, bull_high, bear_low, bear_high


def true_within_lookback(bool_series, i, window):
    """Was `bool_series` True at bar i, or at any of the (window-1) bars
    immediately before it? Only ever looks backward from i, never forward
    -- preserves zero look-ahead exactly like every other concept check in
    this file. window<=1 means strict same-bar (the old default behavior)."""
    if window is None or window <= 1:
        return bool(bool_series.iloc[i])
    start = max(0, i - window + 1)
    return bool(bool_series.iloc[start:i + 1].any())


def breaker_blocks(df, lookback=2):
    """An order block that price later closes through (invalidating it)
    flips polarity into a breaker block. Returns the currently active
    bullish/bearish breaker zone as of each bar. Vectorized (where+ffill
    over the already-vectorized order_blocks() zones) instead of a per-bar
    Python loop -- verified byte-for-byte identical to the old row-by-row
    version across multiple symbols/timeframes."""
    bull_ob_low, bull_ob_high, bear_ob_low, bear_ob_high = order_blocks(df, lookback)
    close = df["close"]

    bear_breaker_trigger = bull_ob_low.notna() & (close < bull_ob_low)
    bull_breaker_trigger = bear_ob_high.notna() & (close > bear_ob_high)

    bear_low = bull_ob_low.where(bear_breaker_trigger).ffill()
    bear_high = bull_ob_high.where(bear_breaker_trigger).ffill()
    bull_low = bear_ob_low.where(bull_breaker_trigger).ffill()
    bull_high = bear_ob_high.where(bull_breaker_trigger).ffill()
    return bull_low, bull_high, bear_low, bear_high
