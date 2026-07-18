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


def _session_group_id(df):
    """Monotonic id incrementing at every session boundary (asian->london,
    london->ny, ny->off_hours, off_hours->next day's asian, ...) -- session
    windows are contiguous in time with no overlap, so "the label changed
    from the previous bar" always lands exactly on a real boundary,
    including the day rollover."""
    session = session_column(df)
    return (session != session.shift(1)).cumsum()


def session_high_low(df):
    """Running high/low of the CURRENT (still-forming) session, reset at
    each session boundary -- causal: an expanding window that only
    reflects bars within this session up to and including the one being
    read, never a peek at where the session eventually finishes."""
    group_id = _session_group_id(df)
    running_high = df.groupby(group_id)["high"].cummax()
    running_low = df.groupby(group_id)["low"].cummin()
    return running_high, running_low


def session_open_price(df):
    """Opening price of the CURRENT session, held constant for every bar of
    that session (the session's first bar's own open, forward-filled) --
    causal, since every bar already knows its own open the instant it
    forms, and a session's first bar's value never changes afterward."""
    group_id = _session_group_id(df)
    return df.groupby(group_id)["open"].transform("first")


def day_of_week_column(df):
    """Day name per bar ('monday'..'sunday'), lowercase -- same role as
    session_column() but for calendar weekday instead of session-of-day,
    for a day-of-week entry filter."""
    return pd.Series(df.index.day_name().str.lower().values, index=df.index)


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


def volume_profile_previous_day(df, bins=24, value_area_pct=0.70):
    """Volume-at-price profile for each COMPLETE UTC day, made available to
    every bar of the FOLLOWING day only (same causal anchoring as
    previous_day_high_low -- yesterday's full session is closed by midnight
    UTC, so today's profile levels never reflect a bar not yet known when
    read).

    For each day, bins that day's volume into `bins` equal-width price
    buckets spanning the day's low-high range, then finds:
      - poc: the bucket midpoint with the single highest volume.
      - vah/val: expanding outward from the POC bucket into whichever
        neighbor has more volume, one bucket at a time, until >=
        value_area_pct of the day's total volume is enclosed (the standard
        Value Area construction) -- vah/val are that enclosed range's
        top/bottom edges.

    Returns (poc, vah, val) as three per-bar Series aligned to df.index."""
    day_key = pd.Series(df.index.date, index=df.index)
    days = sorted(day_key.unique())
    poc_by_day, vah_by_day, val_by_day = {}, {}, {}

    for day in days:
        day_mask = (day_key.values == day)
        day_df = df.loc[day_mask]
        lo, hi = day_df["low"].min(), day_df["high"].max()
        vol_sum = day_df["volume"].sum()
        if hi <= lo or vol_sum <= 0:
            continue
        edges = np.linspace(lo, hi, bins + 1)
        bucket_idx = np.clip(np.digitize(day_df["close"].values, edges) - 1, 0, bins - 1)
        bucket_volume = np.zeros(bins)
        np.add.at(bucket_volume, bucket_idx, day_df["volume"].values)
        centers = (edges[:-1] + edges[1:]) / 2

        poc_i = int(np.argmax(bucket_volume))
        poc_by_day[day] = centers[poc_i]

        total = bucket_volume.sum()
        target = total * value_area_pct
        lo_i = hi_i = poc_i
        enclosed = bucket_volume[poc_i]
        while enclosed < target and (lo_i > 0 or hi_i < bins - 1):
            next_lo = bucket_volume[lo_i - 1] if lo_i > 0 else -1.0
            next_hi = bucket_volume[hi_i + 1] if hi_i < bins - 1 else -1.0
            if next_hi >= next_lo:
                hi_i += 1
                enclosed += bucket_volume[hi_i]
            else:
                lo_i -= 1
                enclosed += bucket_volume[lo_i]
        vah_by_day[day] = edges[hi_i + 1]
        val_by_day[day] = edges[lo_i]

    poc_series = pd.Series(poc_by_day).sort_index()
    vah_series = pd.Series(vah_by_day).sort_index()
    val_series = pd.Series(val_by_day).sort_index()

    poc = day_key.map(poc_series.shift(1))
    vah = day_key.map(vah_series.shift(1))
    val = day_key.map(val_series.shift(1))
    return poc, vah, val


def volume_nodes_previous_day(df, bins=24, low_node_frac=0.25, high_node_frac=1.5):
    """Low/High Volume Nodes from the PREVIOUS complete day's volume
    profile (same causal previous-day anchoring as
    volume_profile_previous_day): a bucket is a Low Volume Node if its
    volume is below low_node_frac x that day's average bucket volume (a
    thin, low-participation price band price tends to move through
    quickly), a High Volume Node if above high_node_frac x average (a
    thick, high-participation band that tends to act like support/
    resistance). Returns (in_lvn, in_hvn): True when the CURRENT bar's
    close falls inside one of yesterday's LVN/HVN price bands."""
    day_key = pd.Series(df.index.date, index=df.index)
    days = sorted(day_key.unique())
    lvn_ranges_by_day, hvn_ranges_by_day = {}, {}

    for day in days:
        day_mask = (day_key.values == day)
        day_df = df.loc[day_mask]
        lo, hi = day_df["low"].min(), day_df["high"].max()
        vol_sum = day_df["volume"].sum()
        if hi <= lo or vol_sum <= 0:
            continue
        edges = np.linspace(lo, hi, bins + 1)
        bucket_idx = np.clip(np.digitize(day_df["close"].values, edges) - 1, 0, bins - 1)
        bucket_volume = np.zeros(bins)
        np.add.at(bucket_volume, bucket_idx, day_df["volume"].values)
        avg = bucket_volume.mean()
        if avg <= 0:
            continue
        lvn_idx = np.where(bucket_volume < low_node_frac * avg)[0]
        hvn_idx = np.where(bucket_volume > high_node_frac * avg)[0]
        lvn_ranges_by_day[day] = [(edges[i], edges[i + 1]) for i in lvn_idx]
        hvn_ranges_by_day[day] = [(edges[i], edges[i + 1]) for i in hvn_idx]

    in_lvn = pd.Series(False, index=df.index)
    in_hvn = pd.Series(False, index=df.index)
    close = df["close"]
    for idx in range(1, len(days)):
        day, prev_day = days[idx], days[idx - 1]
        day_mask = (day_key.values == day)
        day_close = close.loc[day_mask]

        lvn_ranges = lvn_ranges_by_day.get(prev_day, [])
        if lvn_ranges:
            hit = np.zeros(len(day_close), dtype=bool)
            for lo_edge, hi_edge in lvn_ranges:
                hit |= ((day_close >= lo_edge) & (day_close < hi_edge)).values
            in_lvn.loc[day_mask] = hit

        hvn_ranges = hvn_ranges_by_day.get(prev_day, [])
        if hvn_ranges:
            hit = np.zeros(len(day_close), dtype=bool)
            for lo_edge, hi_edge in hvn_ranges:
                hit |= ((day_close >= lo_edge) & (day_close < hi_edge)).values
            in_hvn.loc[day_mask] = hit

    return in_lvn, in_hvn


def aggression(df, volume_period=20, volume_multiplier=1.5, body_ratio=0.6):
    """Directional volume/candle "aggression": a strong-bodied candle (body
    >= body_ratio of the full high-low range) coinciding with a volume
    spike (volume > its rolling average x volume_multiplier) -- one-sided,
    high-conviction participation, which a bare volume spike (volume_filter())
    can't distinguish from an indecisive, small-bodied spike bar."""
    rng = (df["high"] - df["low"]).replace(0, np.nan)
    body = (df["close"] - df["open"]).abs()
    body_frac = (body / rng).fillna(0.0)
    strong_body = body_frac >= body_ratio
    vol_spike = volume_filter(df, volume_period, volume_multiplier)
    bullish = df["close"] > df["open"]
    bearish = df["close"] < df["open"]
    bull_aggression = (strong_body & vol_spike & bullish).fillna(False)
    bear_aggression = (strong_body & vol_spike & bearish).fillna(False)
    return bull_aggression, bear_aggression


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


def mitigation_blocks(df, lookback=2):
    """Like order_blocks(), but the zone is the origin candle's BODY (open
    to close) rather than its full wick range -- the standard distinction:
    an Order Block is measured wick-to-wick, a Mitigation Block by just the
    body, marking a shallower zone price is expected to react at when
    "mitigating" prior imbalance. Same BOS trigger as order_blocks(), just
    a different zone measurement -- so trading it (rather than the wick
    version) means entering closer to the impulsive move, at a tighter
    (and more selective) price."""
    bullish_bos, bearish_bos = break_of_structure(df, lookback)
    bearish_candle = df["close"] < df["open"]
    bullish_candle = df["close"] > df["open"]
    body_low = pd.concat([df["open"], df["close"]], axis=1).min(axis=1)
    body_high = pd.concat([df["open"], df["close"]], axis=1).max(axis=1)

    last_bearish_body_low = body_low.where(bearish_candle).ffill()
    last_bearish_body_high = body_high.where(bearish_candle).ffill()
    last_bullish_body_low = body_low.where(bullish_candle).ffill()
    last_bullish_body_high = body_high.where(bullish_candle).ffill()

    bull_low = last_bearish_body_low.where(bullish_bos).ffill()
    bull_high = last_bearish_body_high.where(bullish_bos).ffill()
    bear_low = last_bullish_body_low.where(bearish_bos).ffill()
    bear_high = last_bullish_body_high.where(bearish_bos).ffill()
    return bull_low, bull_high, bear_low, bear_high


def imbalance(df, lookback=20, ratio=2.0):
    """Single-candle imbalance/inefficiency: one bar's body is unusually
    large (>= ratio x the rolling average body size over the last
    `lookback` bars) -- price was delivered so aggressively in one
    direction that the move is considered "inefficient" and often expected
    to be partially retraced. Deliberately distinct from fair_value_gap()
    (a 3-candle STRUCTURAL gap between non-adjacent wicks): this is a
    single-candle body-size outlier, a different and complementary
    definition also commonly called "imbalance" in real strategy text."""
    body = (df["close"] - df["open"]).abs()
    avg_body = body.rolling(lookback).mean()
    large_body = (body >= ratio * avg_body).fillna(False)
    bullish = df["close"] > df["open"]
    bearish = df["close"] < df["open"]
    bull_imbalance = (large_body & bullish).fillna(False)
    bear_imbalance = (large_body & bearish).fillna(False)
    return bull_imbalance, bear_imbalance


def equal_highs_lows(df, lookback=2, tolerance=0.001):
    """Equal Highs / Equal Lows: two confirmed swing highs (or lows) within
    `tolerance` (fraction of price) of each other -- a classic
    resting-liquidity pool (stops clustered just above equal highs / just
    below equal lows). bull_equal_lows marks the bar where a new swing low
    confirms "equal" to the prior swing low (support-side liquidity, often
    swept before a bullish move); bear_equal_highs mirrors on the
    resistance side."""
    swing_high, swing_low = swing_points(df, lookback)
    high_level = df["high"].where(swing_high)
    low_level = df["low"].where(swing_low)
    prev_high_level = high_level.ffill().shift(1)
    prev_low_level = low_level.ffill().shift(1)

    bear_equal_highs = (
        swing_high & prev_high_level.notna()
        & ((df["high"] - prev_high_level).abs() / prev_high_level <= tolerance)
    ).fillna(False)
    bull_equal_lows = (
        swing_low & prev_low_level.notna()
        & ((df["low"] - prev_low_level).abs() / prev_low_level <= tolerance)
    ).fillna(False)
    return bull_equal_lows, bear_equal_highs


# ------------------------------------------------------------ price action

def engulfing_candle(df):
    """Bullish engulfing: a bearish candle immediately followed by a
    bullish candle whose body fully contains the previous candle's body.
    Bearish engulfing mirrors it."""
    prev_open, prev_close = df["open"].shift(1), df["close"].shift(1)
    prev_bearish = prev_close < prev_open
    prev_bullish = prev_close > prev_open
    cur_bullish = df["close"] > df["open"]
    cur_bearish = df["close"] < df["open"]

    bull_engulf = (
        prev_bearish & cur_bullish & (df["open"] <= prev_close) & (df["close"] >= prev_open)
    ).fillna(False)
    bear_engulf = (
        prev_bullish & cur_bearish & (df["open"] >= prev_close) & (df["close"] <= prev_open)
    ).fillna(False)
    return bull_engulf, bear_engulf


def pin_bar(df, wick_ratio=2.0, body_ratio=0.3):
    """Pin bar / rejection candle: a small body (<= body_ratio of the bar's
    full range) with one wick at least wick_ratio x the body length and
    longer than the opposite wick -- a bullish pin (long lower wick)
    signals rejection of lower prices; a bearish pin (long upper wick) the
    mirror. Requires an actual non-zero body so a pure doji (body == 0)
    can't trivially qualify just from having any wick asymmetry."""
    body = (df["close"] - df["open"]).abs()
    rng = (df["high"] - df["low"]).replace(0, np.nan)
    upper_wick = df["high"] - df[["open", "close"]].max(axis=1)
    lower_wick = df[["open", "close"]].min(axis=1) - df["low"]
    small_body = ((body / rng) <= body_ratio).fillna(False)
    has_body = body > 0

    bull_pin = (
        small_body & has_body & (lower_wick >= wick_ratio * body) & (lower_wick > upper_wick)
    ).fillna(False)
    bear_pin = (
        small_body & has_body & (upper_wick >= wick_ratio * body) & (upper_wick > lower_wick)
    ).fillna(False)
    return bull_pin, bear_pin


def inside_bar(df):
    """Inside bar: current candle's full range contained within the
    previous candle's range -- a consolidation/indecision bar, often used
    as a breakout setup (trade the break of its high/low, or of the
    "mother candle" that contains it). Not inherently directional -- a
    single boolean, unlike the bull/bear pairs above."""
    prev_high, prev_low = df["high"].shift(1), df["low"].shift(1)
    return ((df["high"] <= prev_high) & (df["low"] >= prev_low)).fillna(False)


# ------------------------------------------------------------ exit primitives

def breakeven_stop(entry_price, original_stop, current_price, direction, trigger_rr):
    """Reusable exit primitive: once unrealized profit reaches
    trigger_rr x the ORIGINAL risk (entry_price to original_stop
    distance), the stop should move to breakeven (entry_price) -- never
    moves the stop further away, and never moves it before the trigger is
    actually reached. Returns the new stop-loss price, or None if the
    trigger hasn't been reached yet (the caller should leave the existing
    stop untouched).

    Pure and deliberately stateless -- the caller (ConfiguredStrategy.
    manage_position, called once per bar from the engine's position loop)
    decides WHEN to call this and whether to apply the result, so this
    function itself stays trivially testable in isolation."""
    if original_stop is None or trigger_rr is None or trigger_rr <= 0:
        return None
    risk = abs(entry_price - original_stop)
    if risk <= 0:
        return None
    if direction == "bullish":
        unrealized = current_price - entry_price
    else:
        unrealized = entry_price - current_price
    if unrealized >= trigger_rr * risk:
        return entry_price
    return None
