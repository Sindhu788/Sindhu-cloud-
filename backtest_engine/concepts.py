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


def macd_signal_crossover(macd_line, signal_line):
    """Edge-triggered MACD-line/signal-line crossover: True on ONLY the bar
    the MACD line crosses from at-or-below the signal line to strictly
    above it (bullish) or vice versa (bearish) -- not "is currently above",
    which would stay True for the whole trend leg instead of firing once at
    the actual cross."""
    diff = macd_line - signal_line
    prev_diff = diff.shift(1)
    bullish = ((prev_diff <= 0) & (diff > 0)).fillna(False)
    bearish = ((prev_diff >= 0) & (diff < 0)).fillna(False)
    return bullish, bearish


def macd_zero_crossover(macd_line):
    """Edge-triggered MACD-line/zero-line crossover, same edge-triggered
    convention as macd_signal_crossover()."""
    prev = macd_line.shift(1)
    bullish = ((prev <= 0) & (macd_line > 0)).fillna(False)
    bearish = ((prev >= 0) & (macd_line < 0)).fillna(False)
    return bullish, bearish


def rolling_high(series, period):
    """Highest value of the PRECEDING `period` bars, not including the
    current bar -- shift(1) after the rolling window makes this causal, so
    "close breaks above the previous high zone" never compares a bar's own
    high against a window that includes itself."""
    return series.rolling(period).max().shift(1)


def rolling_low(series, period):
    """Lowest value of the PRECEDING `period` bars, not including the
    current bar -- see rolling_high()."""
    return series.rolling(period).min().shift(1)


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


def previous_session_high_low(df, session_name="asian"):
    """The most recently CLOSED session of type `session_name`'s high/low,
    held constant (forward-filled) from the moment that session ends --
    e.g. the Asian session's range, available during the following London
    session for a liquidity-sweep-of-the-Asian-range setup (Asian Range
    London Sweep). Causal: only ever reflects a session that has fully
    closed, unlike session_high_low() above (the CURRENT, still-forming
    session)."""
    session = session_column(df)
    running_high, running_low = session_high_low(df)
    is_target = (session == session_name)
    prev_high = running_high.where(is_target).ffill()
    prev_low = running_low.where(is_target).ffill()
    return prev_high, prev_low


def session_sweep_reclaim(df, session_name="asian"):
    """Sweep-then-reclaim of a named prior session's range: price sweeps
    below/above the most recently closed `session_name` session's low/high
    (wick or close beyond is enough for the sweep itself), then a LATER
    bar's CLOSE reclaims back inside (edge-triggered -- fires only on the
    bar price transitions back inside, not every bar it stays there).
    Returns (bull_sweep, bear_sweep, bull_reclaim, bear_reclaim) as four
    boolean Series for the caller to compose with sequential_event() to
    enforce the reclaim happening strictly AFTER the sweep."""
    prev_high, prev_low = previous_session_high_low(df, session_name)
    low, high, close = df["low"], df["high"], df["close"]
    bull_sweep = (low < prev_low).fillna(False)
    bear_sweep = (high > prev_high).fillna(False)
    was_below_low = (close.shift(1) <= prev_low.shift(1)).fillna(False)
    was_above_high = (close.shift(1) >= prev_high.shift(1)).fillna(False)
    bull_reclaim = ((close > prev_low) & was_below_low).fillna(False)
    bear_reclaim = ((close < prev_high) & was_above_high).fillna(False)
    return bull_sweep, bear_sweep, bull_reclaim, bear_reclaim


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


def consolidation_impulse_zones(df, consolidation_bars=5, tightness_mult=1.5,
                                 impulse_atr_mult=1.5, atr_period=14):
    """Demand/supply zone: a multi-bar sideways/basing range immediately
    followed by a sharp directional break away from it -- the "consolidation
    then impulse" pattern real supply/demand strategy documents describe,
    which is a genuinely different (and wider) concept than order_blocks()/
    mitigation_blocks() (both anchored to a SINGLE origin candle, not a
    multi-bar range).

    "Tight" is a real, testable measure, not eyeballed: the `consolidation_bars`
    window's own (high-low) range must be no more than `tightness_mult` times
    the AVERAGE SINGLE-bar (high-low) range over the trailing `atr_period`
    bars -- i.e. several bars packed together barely exceed what one normal
    bar's range would be, which is what "sideways" actually means (real
    overlap between bars), as opposed to a tight staircase that is still
    trending.

    "Sharp"/impulsive is likewise real and testable: the very next bar's
    close-to-close move must be at least `impulse_atr_mult` x ATR(atr_period)
    in one direction, AND that bar's close must actually clear the
    consolidation window's high (bullish) or low (bearish) -- a big bar that
    doesn't even escape the range isn't an impulse away from it.

    The zone marked is the consolidation window's own low-to-high (the
    source document's "candle right before the impulse move," generalized
    from a single candle to the whole basing window since this pattern is
    inherently multi-bar).

    Returns (demand_low, demand_high, supply_low, supply_high), each
    forward-filled from the most recently confirmed zone -- NaN until the
    first one forms. Demand = consolidation before an UP impulse (support
    zone below future price). Supply = consolidation before a DOWN impulse
    (resistance zone above future price)."""
    high, low, close = df["high"], df["low"], df["close"]
    atr_val = atr(df, atr_period)
    avg_single_bar_range = (high - low).rolling(atr_period).mean()

    window_high = high.rolling(consolidation_bars).max()
    window_low = low.rolling(consolidation_bars).min()
    window_range = window_high - window_low
    is_tight = (window_range <= tightness_mult * avg_single_bar_range).fillna(False)

    move = close - close.shift(1)
    # The consolidation window is evaluated as of the PREVIOUS bar (it must
    # have already finished being tight before the impulse bar breaks away
    # from it) -- shift(1) on both the tightness flag and the window
    # boundaries keeps this causal: bar i's zone only ever uses information
    # confirmed by the close of bar i-1.
    prior_tight = is_tight.shift(1).fillna(False)
    prior_window_high = window_high.shift(1)
    prior_window_low = window_low.shift(1)

    is_impulse_up = (move >= impulse_atr_mult * atr_val) & (close > prior_window_high)
    is_impulse_down = ((-move) >= impulse_atr_mult * atr_val) & (close < prior_window_low)

    demand_trigger = (prior_tight & is_impulse_up.fillna(False))
    supply_trigger = (prior_tight & is_impulse_down.fillna(False))

    demand_low = prior_window_low.where(demand_trigger).ffill()
    demand_high = prior_window_high.where(demand_trigger).ffill()
    supply_low = prior_window_low.where(supply_trigger).ffill()
    supply_high = prior_window_high.where(supply_trigger).ffill()
    return demand_low, demand_high, supply_low, supply_high


def valid_structure_trend(df, lookback=2):
    """"Valid low/high" structural trend: a swing low only becomes
    structurally VALID once price subsequently closes above the swing high
    that existed before it formed; the trend is only considered to have
    flipped once that specific valid low is later broken by a close below
    it -- NOT on every minor lower low that never actually broke a prior
    high. Symmetric for valid highs breaking a prior valid low to flip back
    up.

    This is a genuinely sequential, stateful rule -- whether a given low
    "counts" depends on a specific LATER event (a break of the specific
    high that predates it), which cannot be expressed with the
    where()/ffill() vectorization every other concept in this module uses
    (those only ever look at each bar's own recent window, never "the next
    time a specific earlier reference level gets broken"). This is
    deliberately a plain, per-bar Python loop instead of a vectorized
    one -- correct sequential state, not a vectorized approximation of it.
    Cost is linear in the number of bars, which is fine at the bar counts
    this engine actually backtests (thousands to tens of thousands of
    1h/15m/5m bars per symbol).

    Returns a single pandas Series of "up" / "down" / None per bar
    (forward-implied by the state machine, not literally forward-filled --
    None only before the very first valid low or high has ever formed)."""
    swing_high, swing_low = swing_points(df, lookback)
    high, low, close = df["high"].values, df["low"].values, df["close"].values
    sh, sl = swing_high.values, swing_low.values
    n = len(df)

    trend = None
    valid_low = None
    valid_high = None
    pending_low = None
    pending_low_break_level = None
    pending_high = None
    pending_high_break_level = None
    last_swing_high = None
    last_swing_low = None

    out = [None] * n
    for i in range(n):
        c = close[i]

        # 1. Did this bar's close break the currently-active valid low/high?
        #    (checked BEFORE this bar's own swing-point bookkeeping, since a
        #    flip and a new pending point can legitimately happen on the
        #    same bar.)
        if trend == "up" and valid_low is not None and c < valid_low:
            trend = "down"
            valid_low = None
            valid_high = None
        elif trend == "down" and valid_high is not None and c > valid_high:
            trend = "up"
            valid_high = None
            valid_low = None

        # 2. Track the most recent swing points seen so far, and open a
        #    "pending" validation slot for a fresh swing low/high -- it only
        #    becomes VALID once a later close breaks the opposite swing
        #    level that existed at the moment this one formed.
        #    swing_points() marks sl[i]/sh[i] True `lookback` bars AFTER the
        #    actual pivot bar (it needs that many bars on both sides to
        #    confirm the pivot) -- the real price belongs to bar i-lookback,
        #    not to bar i itself.
        if sl[i]:
            pivot = i - lookback
            pending_low = low[pivot]
            pending_low_break_level = last_swing_high
            last_swing_low = low[pivot]
        if sh[i]:
            pivot = i - lookback
            pending_high = high[pivot]
            pending_high_break_level = last_swing_low
            last_swing_high = high[pivot]

        # 3. Does this bar's close confirm a pending low/high as VALID?
        if pending_low is not None and pending_low_break_level is not None and c > pending_low_break_level:
            valid_low = pending_low
            pending_low = None
            if trend is None:
                trend = "up"
        if pending_high is not None and pending_high_break_level is not None and c < pending_high_break_level:
            valid_high = pending_high
            pending_high = None
            if trend is None:
                trend = "down"

        out[i] = trend

    return pd.Series(out, index=df.index, dtype=object)


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


def sequential_event(event_a, event_b, max_gap=None, reset_key=None):
    """Genuine event ORDERING, not co-occurrence: True at bar j only if
    event_b fires at j AND event_a fired at some STRICTLY EARLIER bar i < j
    (optionally within max_gap bars), with no requirement that a fires
    again for every b -- the most recent a "carries forward" the same way
    valid_structure_trend()'s state does. This is the primitive the old
    window-based concept check (ConfiguredStrategy._eval()'s _within(),
    which only asks "did THIS SAME event happen anywhere in the last N
    bars", independently per condition, with no ordering between two
    DIFFERENT conditions) cannot express: b-then-a in the same window would
    incorrectly pass a co-occurrence check but must NOT pass this one.

    reset_key: optional per-bar grouping key Series (e.g. a trading-day
    date, for a strategy whose own rules require "setups and re-entries
    must occur within the same day" -- 4-Hour Range Breakout-Retest).
    When provided, an earlier event_a occurrence only counts if it shares
    the SAME key as the current bar j -- an event_a from a previous
    day/session can never pair with a later day's event_b. None (default,
    every caller before this parameter existed -- CRT 2.0, Double
    Confirmation CHoCH) means no reset, exactly the original behavior.

    A real per-bar loop (not a vectorized shift/ffill trick) so the
    ordering logic is impossible to get subtly backwards -- same
    conservative choice as valid_structure_trend() after its own indexing
    bug was found there."""
    a = event_a.fillna(False).to_numpy()
    b = event_b.fillna(False).to_numpy()
    keys = reset_key.to_numpy() if reset_key is not None else None
    n = len(a)
    out = [False] * n
    last_a_idx = None
    last_a_key = None
    for i in range(n):
        # Check b[i] against the state as of the END of the PREVIOUS bar,
        # before this bar's own a[i] can update it -- event_a and event_b
        # are not always mutually exclusive (e.g. a single candle can both
        # sweep AND reclaim at once), so updating last_a_idx first would
        # let bar i's own a[i]=True silently overwrite a genuinely earlier,
        # still-valid event_a -- checked before this fix and confirmed on
        # real Asian Range London Sweep data: a legitimate sweep at bar 200
        # failed to pair with its reclaim at bar 229 purely because bar
        # 229 ALSO happened to satisfy event_a, clobbering the reference to
        # bar 200 one line too early.
        if b[i] and last_a_idx is not None and i > last_a_idx:
            if keys is None or keys[i] == last_a_key:
                if max_gap is None or (i - last_a_idx) <= max_gap:
                    out[i] = True
        if a[i]:
            last_a_idx = i
            if keys is not None:
                last_a_key = keys[i]
    return pd.Series(out, index=event_a.index, dtype=bool)


def sweep_invalidation_state(bull_event, bear_event):
    """State machine for "setup active on one side until the OPPOSITE event
    invalidates it": long_setup_active is True from the bar after a
    bull_event fires until a bear_event fires (which flips to
    short_setup_active instead), and vice versa -- exactly the CRT 2.0
    invalidation rule ("sweeps the bottom and closes inside, but then
    sweeps the top and closes inside before entry triggers -> setup is
    invalid, wait for a new candle"). A bull and bear event on the SAME bar
    is a genuinely contradictory bar (like _eval_long_short/_eval_rule_
    groups elsewhere in this codebase) -- treated as invalidating whatever
    was pending rather than arbitrarily picking a side."""
    bull = bull_event.fillna(False).to_numpy()
    bear = bear_event.fillna(False).to_numpy()
    n = len(bull)
    state = None
    out = [None] * n
    for i in range(n):
        if bull[i] and bear[i]:
            state = None
        elif bull[i]:
            state = "long"
        elif bear[i]:
            state = "short"
        out[i] = state
    result = pd.Series(out, index=bull_event.index, dtype=object)
    return result == "long", result == "short"


def level_sweep_reclaim(df, lookback=2):
    """Generic sweep-then-reclaim of the nearest swing support/resistance
    level (same anchor as liquidity_sweep() above), but -- unlike
    liquidity_sweep(), which requires the wick-beyond AND close-back-inside
    on the SAME bar -- allows the reclaim on a LATER bar (Liquidity Sweep
    Reversal Strategy's explicit "the sweep alone is NOT a signal; a
    subsequent candle must reclaim"). Returns (bull_sweep, bear_sweep,
    bull_reclaim, bear_reclaim) for the caller to compose with
    sequential_event() to enforce strict ordering."""
    support, resistance = support_resistance(df, lookback)
    low, high, close = df["low"], df["high"], df["close"]
    bull_sweep = (low < support).fillna(False)
    bear_sweep = (high > resistance).fillna(False)
    was_below = (close.shift(1) <= support.shift(1)).fillna(False)
    was_above = (close.shift(1) >= resistance.shift(1)).fillna(False)
    bull_reclaim = ((close > support) & was_below).fillna(False)
    bear_reclaim = ((close < resistance) & was_above).fillna(False)
    return bull_sweep, bear_sweep, bull_reclaim, bear_reclaim


def ema_no_touch_trigger(df, ema):
    """"Trigger candle" for the Laxman Rekha 5-EMA strategy: a candle where
    NEITHER the high nor the low touches the EMA line -- forms entirely
    below it (bullish trigger) or entirely above it (bearish trigger).
    Candle colour is deliberately irrelevant to this definition (the source
    only describes the candle's position relative to the EMA, not its
    open/close relationship)."""
    below = ((df["high"] < ema) & (df["low"] < ema)).fillna(False)
    above = ((df["low"] > ema) & (df["high"] > ema)).fillna(False)
    return below, above


def reaction_at_level(df, support_level, resistance_level):
    """Wick beyond a given EXTERNAL support/resistance level (already
    aligned onto this frame's index, typically a higher-timeframe level
    merged via MultiTimeframeContext) with the candle's close failing to
    sustain beyond it -- the "reaction" event used by Dumb Money Concepts'
    Confirmation entry (reaction, then a later retest of the same level).
    Same wick-vs-close shape as liquidity_sweep(), but that function derives
    its level from THIS frame's own swing points; this one takes an
    already-known external level instead, since DMC's levels come from a
    higher timeframe (Monthly/Weekly/Daily) than its 4H reaction/entry
    timeframe."""
    low, high, close = df["low"], df["high"], df["close"]
    bullish_reaction = ((low < support_level) & (close > support_level)).fillna(False)
    bearish_reaction = ((high > resistance_level) & (close < resistance_level)).fillna(False)
    return bullish_reaction, bearish_reaction


def next_prior_swing_level(df, lookback=2):
    """For each bar, the swing low/high value that was confirmed BEFORE the
    current active one -- i.e. "the next level further out" behind the
    current support/resistance. Used for Dumb Money Concepts' stop-loss
    ("behind the next level behind" the entry level). Same swing-point
    anchor as support_resistance()/swing_points(), just one occurrence
    further back: the sparse series of swing-low/high VALUES (not the
    per-bar forward-filled one) is shifted by one occurrence, then
    forward-filled back onto every bar."""
    swing_high, swing_low = swing_points(df, lookback)
    low_at_swings = df["low"].where(swing_low).dropna()
    high_at_swings = df["high"].where(swing_high).dropna()

    prev_low = pd.Series(index=df.index, dtype=float)
    prev_low.loc[low_at_swings.index] = low_at_swings.shift(1)
    prev_low = prev_low.ffill()

    prev_high = pd.Series(index=df.index, dtype=float)
    prev_high.loc[high_at_swings.index] = high_at_swings.shift(1)
    prev_high = prev_high.ffill()
    return prev_low, prev_high


def move_origin_target(df, lookback=2):
    """A representable stand-in for "the origin of the move that brought
    price to this level" (Dumb Money Concepts' primary take-profit target):
    the OPPOSING structural level that was active at the exact moment the
    current active support/resistance was itself confirmed -- for a support
    level, this is the resistance value in effect when that swing low
    formed (the high the down-move came FROM); mirrored for resistance.
    Own default: the source's own definition of "origin" is a discretionary
    chart-reading judgment with no mechanical rule given, so this uses the
    nearest opposing confirmed swing structure at that moment as the
    closest honestly-representable equivalent, rather than guessing at a
    more elaborate rule the source never actually specifies."""
    swing_high, swing_low = swing_points(df, lookback)
    support, resistance = support_resistance(df, lookback)
    origin_for_support = resistance.where(swing_low).ffill()
    origin_for_resistance = support.where(swing_high).ffill()
    return origin_for_support, origin_for_resistance


def level_touch(df, support_level, resistance_level):
    """Immediate touch of an external support/resistance level -- no wick-
    vs-close reaction required (contrast with reaction_at_level(), which
    also requires the close to fail beyond the level). Dumb Money Concepts'
    "Blind Entry" variant: enter the instant price first reaches an
    untested level, with no confirmation candle at all."""
    low, high = df["low"], df["high"]
    bull_touch = (low <= support_level).fillna(False)
    bear_touch = (high >= resistance_level).fillna(False)
    return bull_touch, bear_touch


def within_level_zone(df, level_series, atr_series, frac=0.25):
    """Whether the candle's close falls within a small ATR-scaled buffer
    band around an external level -- a single-entry approximation of Dumb
    Money Concepts' "DCA zone" (top/bottom of a zone around the level).
    This does NOT implement actual multi-entry/DCA averaging (see
    ENGINE_GAP_TRACKER.md gap #14, still excluded); it only widens the
    single retest-entry trigger from "exactly at the level" to "within a
    band around it," a own-default approximation since the source gives no
    exact zone width -- frac=0.25 (a quarter of ATR) is this builder's own
    default for a "small" band."""
    buf = atr_series * frac
    close = df["close"]
    return ((close >= level_series - buf) & (close <= level_series + buf)).fillna(False)


def first_signal_per_level(signal_event, level_series):
    """A signal event only counts the FIRST time it fires while
    `level_series` holds a given value -- once used (whether the resulting
    trade wins or loses), that exact level is retired: later signal_event
    firings against the SAME level value are suppressed until level_series
    changes to a genuinely new value. Dumb Money Concepts' "once-tested"
    rule ("each specific level can only trigger one trade"). Exact float
    equality is safe here since level_series only ever carries forward the
    SAME stored value via ffill (see support_resistance()), never
    recomputes it -- there is no floating-point drift to worry about."""
    sig = signal_event.fillna(False).to_numpy()
    levels = level_series.to_numpy()
    n = len(sig)
    out = [False] * n
    used_level = None
    for i in range(n):
        lvl = levels[i]
        if not sig[i] or lvl is None or (isinstance(lvl, float) and np.isnan(lvl)):
            continue
        if lvl != used_level:
            out[i] = True
            used_level = lvl
    return pd.Series(out, index=signal_event.index, dtype=bool)


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

    Edge-triggered, not level-triggered (Task 3, Priority Batch 1): a break
    fires True on ONLY the first bar that trades past the reference
    candle's extreme, not on every subsequent bar that also happens to
    still be beyond it. Diagnosed live against real data (PDH-PDL Signal
    Candle Strategy's 119,255-trade / 1.62%-win backtest): the previous
    version's `bear_break`/`bull_break` stayed True for as long as price
    kept making fresh lows/highs past a stale reference candle, so a single
    multi-bar move re-armed a "new" entry signal on every one of those bars
    once the strategy was flat again, not just once -- inflating trade
    count well beyond what "wait for a break" actually describes. Each
    reference candle (tracked via a running count of bullish/bearish
    candles) may now only ever produce one break event.

    Causal by construction: the reference high/low is shifted one bar
    before comparison, so a candle can never trigger a break of itself and
    nothing reads a value that wasn't already closed."""
    bullish = df["close"] > df["open"]
    bearish = df["close"] < df["open"]
    # Most recent bullish/bearish candle's extreme, as known BEFORE this bar.
    last_bull_high = df["high"].where(bullish).ffill().shift(1)
    last_bear_low = df["low"].where(bearish).ffill().shift(1)
    raw_bull_break = (df["high"] > last_bull_high).fillna(False)
    raw_bear_break = (df["low"] < last_bear_low).fillna(False)
    # Which reference candle each bar is being tested against -- shift(1)
    # here matches the shift(1) already baked into last_bull_high/
    # last_bear_low above, so a bar that is itself bearish (and therefore
    # becomes tomorrow's reference) is still grouped by the OLDER reference
    # it's actually being compared against right now, not the new one it's
    # simultaneously creating. Only the first True within a given reference
    # candle's group counts as the actual break event; later bars waiting
    # on that same still-unbroken-again reference are already-fired
    # duplicates, not new signals.
    bull_ref_id = bullish.cumsum().shift(1)
    bear_ref_id = bearish.cumsum().shift(1)
    bull_break = raw_bull_break & (raw_bull_break.groupby(bull_ref_id).cumsum() == 1)
    bear_break = raw_bear_break & (raw_bear_break.groupby(bear_ref_id).cumsum() == 1)
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


# ------------------------------------------------------------ Advanced Concept Library expansion
#
# Premium & Discount Zones, Rejection Block, Cumulative Volume Delta,
# Opening Range Breakout, Initial Balance, Anchored VWAP, and Kill Zones.
# (Breaker Block, Mitigation Block, and Equal Highs/Equal Lows were already
# implemented above -- see breaker_blocks(), mitigation_blocks(),
# equal_highs_lows() -- so are reused as-is rather than reimplemented.)
# Same rules as everything else in this file: pure, vectorized, causal.

def premium_discount_zone(df, lookback=2):
    """ICT-style Premium/Discount Zones: whether the current close sits in
    the lower half (discount -- favorable to look for buys) or upper half
    (premium -- favorable to look for sells) of the most recently CONFIRMED
    swing-high-to-swing-low range, split at its midpoint (equilibrium).
    Reuses swing_points()'s already-causal confirmation delay -- the range
    only updates once a swing is confirmed, never on the still-forming bar.
    Returns (in_discount, in_premium) boolean Series."""
    swing_high, swing_low = swing_points(df, lookback)
    recent_high = df["high"].where(swing_high).ffill()
    recent_low = df["low"].where(swing_low).ffill()
    equilibrium = (recent_high + recent_low) / 2
    in_discount = (df["close"] < equilibrium).fillna(False)
    in_premium = (df["close"] > equilibrium).fillna(False)
    return in_discount, in_premium


def rejection_blocks(df, lookback=2, wick_ratio=2.0):
    """Rejection Block: at a confirmed swing low, the zone from that
    candle's low up to its body's lower edge, on a candle with a long lower
    wick (wick >= wick_ratio x body) -- the area price was sharply
    REJECTED FROM. Mirrors on the upside at a confirmed swing high with a
    long upper wick. Distinct from Order Block (origin candle's full body,
    confirmed by a later BOS) and Mitigation Block (same, but body-only) --
    a Rejection Block is anchored to the wick itself and to the swing
    point directly, not to a later break of structure. A doji (body == 0)
    with any wick at all counts as an infinitely strong rejection, matching
    pin_bar()'s treatment of the same edge case.
    Returns (bull_low, bull_high, bear_low, bear_high) -- forward-filled
    from the last confirmed rejection, NaN until the first one."""
    swing_high, swing_low = swing_points(df, lookback)
    body_top = df[["open", "close"]].max(axis=1)
    body_bottom = df[["open", "close"]].min(axis=1)
    body = (df["close"] - df["open"]).abs()
    lower_wick = body_bottom - df["low"]
    upper_wick = df["high"] - body_top

    strong_lower = ((lower_wick >= wick_ratio * body) | ((body == 0) & (lower_wick > 0))).fillna(False)
    strong_upper = ((upper_wick >= wick_ratio * body) | ((body == 0) & (upper_wick > 0))).fillna(False)

    bull_trigger = swing_low & strong_lower
    bear_trigger = swing_high & strong_upper

    bull_low = df["low"].where(bull_trigger).ffill()
    bull_high = body_bottom.where(bull_trigger).ffill()
    bear_low = body_top.where(bear_trigger).ffill()
    bear_high = df["high"].where(bear_trigger).ffill()
    return bull_low, bull_high, bear_low, bear_high


def cumulative_volume_delta(df):
    """Cumulative Volume Delta (CVD), approximated from OHLCV bars -- this
    system stores only standard exchange candles (see data_engine/storage.py),
    not bid/ask-classified trade prints, so a genuine tick-level delta
    cannot be computed here. The standard OHLCV approximation is used
    instead: a bar's full volume counts as buy-side (+) if it closed up,
    sell-side (-) if it closed down, and zero if unchanged (a doji), then
    cumulatively summed within each UTC day (reset at each day boundary,
    the same anchoring as vwap_daily()) so CVD reads as "today's net
    buy/sell pressure so far" rather than drifting forever. This is a
    real, commonly-used approximation, not the true order-flow figure --
    documented here rather than silently presented as exact."""
    signed_volume = pd.Series(
        np.where(df["close"] > df["open"], df["volume"],
                 np.where(df["close"] < df["open"], -df["volume"], 0.0)),
        index=df.index,
    )
    day_key = pd.Series(df.index.date, index=df.index)
    return signed_volume.groupby(day_key).cumsum()


def _first_window_range(df, window_minutes):
    """Shared mechanism for Opening Range and Initial Balance: the
    high/low established in the first `window_minutes` of each UTC day.
    Expanding-window cummax/cummin inside the window (causal -- only
    reflects bars seen so far this window). NOTE: unlike a plain (non-
    grouped) Series.cummax(), pandas' groupby().cummax()/cummin() do NOT
    carry the last valid value through NaN -- they leave the NaN positions
    NaN (verified directly; this is not the ungrouped method's behavior).
    So the window's final value must be explicitly forward-filled to hold
    for the rest of that day, per day (grouped ffill, so day N's range
    can never leak into day N+1)."""
    day_key = pd.Series(df.index.date, index=df.index)
    minutes_since_midnight = df.index.hour * 60 + df.index.minute
    in_window = minutes_since_midnight < window_minutes
    win_high = df["high"].where(in_window).groupby(day_key).cummax().groupby(day_key).ffill()
    win_low = df["low"].where(in_window).groupby(day_key).cummin().groupby(day_key).ffill()
    return win_high, win_low


def _first_window_range_tz(df, window_minutes, tz="America/New_York"):
    """Same mechanism as _first_window_range(), but the day boundary and
    "minutes since midnight" are computed in `tz` instead of UTC -- needed
    for a strategy whose own rules require a specific non-UTC session (e.g.
    4-Hour Range Breakout-Retest: "set chart timezone to New York time to
    identify the correct first candle of the day"). Requires a tz-aware
    index (true for this engine's real OHLCV data, which is UTC-localized).
    UTC's own _first_window_range() is unaffected/unchanged -- this is a
    separate function, not a modification of it."""
    local_index = df.index.tz_convert(tz)
    day_key = pd.Series(local_index.date, index=df.index)
    minutes_since_midnight = local_index.hour * 60 + local_index.minute
    in_window = minutes_since_midnight < window_minutes
    win_high = df["high"].where(in_window).groupby(day_key).cummax().groupby(day_key).ffill()
    win_low = df["low"].where(in_window).groupby(day_key).cummin().groupby(day_key).ffill()
    return win_high, win_low


def four_hour_range(df, tz="America/New_York"):
    """The high/low of the FIRST 4-hour candle of the trading day, in `tz`
    (default New York, matching this strategy's own explicit requirement).
    window_minutes=240 = 4 hours."""
    return _first_window_range_tz(df, 240, tz)


def four_hour_range_breakout(df, tz="America/New_York"):
    """Bull/bear breakout beyond four_hour_range(): a bar's CLOSE (never a
    mere wick -- matches the source's explicit "wicks alone do not count,
    a full candle body close beyond the range is required") beyond the
    range, only AFTER the 4-hour window has fully closed for that day (a
    still-forming range can't be broken yet) -- same convention as
    opening_range_breakout()."""
    range_high, range_low = four_hour_range(df, tz)
    local_index = df.index.tz_convert(tz)
    minutes_since_midnight = local_index.hour * 60 + local_index.minute
    window_closed = minutes_since_midnight >= 240
    bull_break = (window_closed & (df["close"] > range_high)).fillna(False)
    bear_break = (window_closed & (df["close"] < range_low)).fillna(False)
    return bull_break, bear_break


def range_reentry_event(df, range_high, range_low):
    """Edge-triggered "closed back inside the range" event: True only on
    the bar price transitions from outside to inside [range_low,
    range_high] -- not every bar it happens to still be inside (which
    would make concepts.sequential_event() match on every subsequent bar
    instead of just the actual re-entry moment)."""
    close = df["close"]
    in_range = (close >= range_low) & (close <= range_high)
    was_inside = in_range.shift(1).fillna(False).astype(bool)
    return (in_range & ~was_inside).fillna(False)


def opening_range(df, range_minutes=30):
    """Opening Range: the high/low established in the first `range_minutes`
    minutes of each UTC trading day -- the range an Opening Range Breakout
    (ORB) strategy waits for price to break out of."""
    return _first_window_range(df, range_minutes)


def opening_range_breakout(df, range_minutes=30):
    """ORB: price closes above/below the Opening Range, but only AFTER the
    opening window has fully closed -- a still-forming range can't be
    "broken" yet, so breakouts are only flagged once
    minutes_since_midnight >= range_minutes for that bar."""
    or_high, or_low = opening_range(df, range_minutes)
    minutes_since_midnight = df.index.hour * 60 + df.index.minute
    window_closed = minutes_since_midnight >= range_minutes
    bull_break = (window_closed & (df["close"] > or_high)).fillna(False)
    bear_break = (window_closed & (df["close"] < or_low)).fillna(False)
    return bull_break, bear_break


def initial_balance(df, ib_minutes=60):
    """Initial Balance (IB): market-profile terminology for the high/low
    range established in the first `ib_minutes` of the UTC trading day
    (conventionally 60 minutes / the first two 30-minute TPO periods) --
    distinct from the shorter Opening Range typically used for ORB
    breakout strategies, and read as a day-structure reference rather than
    a single breakout trigger. Same underlying mechanism as opening_range(),
    just a different conventional window."""
    return _first_window_range(df, ib_minutes)


def initial_balance_extension(df, ib_minutes=60):
    """Whether the close is currently trading outside the Initial Balance
    range (above or below) -- an "IB extension", commonly read as an early
    sign of a trending (vs. balanced/rotational) day."""
    ib_high, ib_low = initial_balance(df, ib_minutes)
    above = (df["close"] > ib_high).fillna(False)
    below = (df["close"] < ib_low).fillna(False)
    return above, below


def anchored_vwap(df, anchor="swing_low", lookback=2):
    """VWAP anchored to the most recently CONFIRMED swing low or swing high
    (anchor="swing_low" or "swing_high"), instead of resetting at a fixed
    calendar boundary like vwap_daily() -- the common real-world usage
    ("VWAP from the last swing low"). The running sum resets every time a
    new anchor point confirms, so the anchor used at any bar is always the
    most recent one already known as of that bar -- never a future swing
    point later bars would reveal. Bars before the FIRST anchor point has
    ever confirmed have no valid anchor and are NaN, rather than silently
    anchoring to the start of the whole dataset."""
    if anchor not in ("swing_low", "swing_high"):
        raise ValueError("anchor must be 'swing_low' or 'swing_high'")
    swing_high, swing_low = swing_points(df, lookback)
    anchor_mask = swing_low if anchor == "swing_low" else swing_high
    anchor_id = anchor_mask.cumsum()  # increments starting at each new anchor bar (inclusive)

    typical = (df["high"] + df["low"] + df["close"]) / 3
    pv = typical * df["volume"]
    cum_pv = pv.groupby(anchor_id).cumsum()
    cum_vol = df["volume"].groupby(anchor_id).cumsum()
    result = cum_pv / cum_vol.replace(0, np.nan)
    return result.where(anchor_id > 0)


_KILL_ZONE_WINDOWS_UTC = [
    ("london_kz", 7, 10),
    ("ny_kz", 12, 15),
]


def kill_zone_column(df):
    """ICT-style Kill Zones: narrow, high-liquidity windows around the
    London and New York session opens -- distinct from the broader,
    whole-session session_column() windows. Fixed-hour approximation, same
    vectorized shape as session_column()."""
    hours = df.index.hour.values
    conditions = [(hours >= start) & (hours < end) for _, start, end in _KILL_ZONE_WINDOWS_UTC]
    choices = [name for name, _, _ in _KILL_ZONE_WINDOWS_UTC]
    return pd.Series(np.select(conditions, choices, default="none"), index=df.index)


def in_kill_zone(df):
    """True whenever the bar falls inside ANY kill zone window."""
    return kill_zone_column(df) != "none"


# ------------------------------------------------------------ price action

def doji_pattern(df, max_body_pct=10.0):
    """Doji: a candle whose body is at most max_body_pct of its own full
    high-low range -- "very small" from the source, no exact number given
    (own default, flagged by the caller). Not inherently directional; a
    single boolean, the same shape as inside_bar()."""
    body = (df["close"] - df["open"]).abs()
    rng = (df["high"] - df["low"]).replace(0, np.nan)
    body_pct = (body / rng * 100)
    return (body_pct <= max_body_pct).fillna(False)


def morning_evening_star(df, small_body_max_pct=30.0):
    """Morning Star (bullish): a large red candle, then a small-bodied
    indecision candle, then a large green candle -- self-confirming
    three-candle reversal (no separate confirmation candle needed, unlike
    Doji/Hammer/Shooting Star). Evening Star mirrors it. "Large" candle =
    body_pct > small_body_max_pct (the same threshold, inverted, as the
    middle candle's own smallness test)."""
    body = (df["close"] - df["open"]).abs()
    rng = (df["high"] - df["low"]).replace(0, np.nan)
    body_pct = (body / rng * 100)
    is_small_body = (body_pct <= small_body_max_pct).fillna(False)
    is_large_body = (body_pct > small_body_max_pct).fillna(False)
    bearish = df["close"] < df["open"]
    bullish = df["close"] > df["open"]

    c1_bearish_large = (bearish & is_large_body).shift(2).fillna(False)
    c1_bullish_large = (bullish & is_large_body).shift(2).fillna(False)
    c2_small = is_small_body.shift(1).fillna(False)
    c3_bullish_large = bullish & is_large_body
    c3_bearish_large = bearish & is_large_body

    morning_star = (c1_bearish_large & c2_small & c3_bullish_large).fillna(False)
    evening_star = (c1_bullish_large & c2_small & c3_bearish_large).fillna(False)
    return morning_star, evening_star


def candle_pattern_confirmation(pattern_event, df, direction):
    """Generic "a candlestick pattern fires, THEN a later candle confirms
    by closing beyond the PATTERN candle's own high (bullish) or low
    (bearish)" -- used for Doji/Hammer/Shooting Star (Engulfing/Star
    patterns are self-confirming and don't need this). The pattern
    candle's own extreme is carried forward (where+ffill, same convention
    as fvg_zone()/order_blocks()) so a LATER bar can compare against the
    SPECIFIC pattern candle's level, not just "any recent candle's" --
    then concepts.sequential_event() enforces the confirmation happening
    strictly AFTER the pattern bar, not on/before it."""
    if direction == "bullish":
        pending_level = df["high"].where(pattern_event).ffill()
        raw_confirm = (df["close"] > pending_level).fillna(False)
    else:
        pending_level = df["low"].where(pattern_event).ffill()
        raw_confirm = (df["close"] < pending_level).fillna(False)
    # Edge-triggered (fires only the FIRST bar price closes beyond the
    # pattern's level, not every subsequent bar it stays there) -- without
    # this, sequential_event()'s state-carries-forward semantics would
    # re-signal "confirmed" on every later bar too, the same over-trading
    # bug found and fixed for CRT 2.0's FVG re-entry check earlier this
    # session.
    was_confirmed = raw_confirm.shift(1).fillna(False).astype(bool)
    raw_confirm_edge = raw_confirm & ~was_confirmed
    return sequential_event(pattern_event, raw_confirm_edge)


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


# ------------------------------------------------------------ New Batch 3 (3 strategies)

def trend_regime(df, ema_period=50, atr_period=14, sideways_atr_mult=0.5):
    """3-way trend classification -- "up" / "down" / "sideways" -- for
    strategies that need to explicitly SKIP a genuinely unclear/ranging
    market, which trend_filter() above (a plain 2-way close-vs-EMA split,
    always either "up" or "down", never neutral) cannot express.

    Own default (no source gives an exact numeric rule for "sideways"):
    price sitting within `sideways_atr_mult` x ATR of its own EMA is
    "hugging the average" -- no clear directional edge over current
    volatility -- classified "sideways" regardless of which side of the EMA
    it's technically on. Outside that band, "up"/"down" by which side of
    the EMA price is on, same as trend_filter(). Reuses ema()/atr()
    directly, no new primitive invented for either half of the calculation."""
    ma = ema(df["close"], ema_period)
    atr_val = atr(df, atr_period)
    diff = df["close"] - ma
    band = sideways_atr_mult * atr_val
    state = np.where(diff.abs() <= band, "sideways", np.where(diff > 0, "up", "down"))
    return pd.Series(state, index=df.index, dtype=object)


def order_block_validity(df, lookback=2):
    """Whether each bar's currently-active bull/bear Order Block (from
    order_blocks()) is still VALID, or has already been invalidated by
    price closing back through it before any trade used it -- "if price
    moves past a marked Order Block before an entry occurs, that OB becomes
    invalid" (New Batch 3, Strategy 3's own explicit mitigation rule).

    Reuses the EXACT same close-through-the-zone trigger breaker_blocks()
    above already computes for the OB->breaker polarity flip -- this just
    exposes it as a plain per-bar valid/invalid flag instead of a new
    breaker zone, so no invalidation logic is duplicated. An invalidation
    clears automatically the instant a NEW Order Block replaces the old one
    (a fresh BOS), since that is a genuinely different zone becoming
    active, not the same one becoming valid again -- tracked via a block-id
    that increments each time the active OB's own edge value changes, so
    `groupby(...).cummax()` only accumulates "has THIS specific zone ever
    been breached" within its own lifetime. Fully vectorized (no per-bar
    Python loop needed, unlike the genuinely sequential concepts above)."""
    bull_low, bull_high, bear_low, bear_high = order_blocks(df, lookback)
    close = df["close"]

    bull_trigger = (bull_low.notna() & (close < bull_low))
    bear_trigger = (bear_high.notna() & (close > bear_high))

    bull_block_id = (bull_low != bull_low.shift(1)).cumsum()
    bear_block_id = (bear_high != bear_high.shift(1)).cumsum()

    bull_invalidated = bull_trigger.groupby(bull_block_id).cummax().fillna(False).astype(bool)
    bear_invalidated = bear_trigger.groupby(bear_block_id).cummax().fillna(False).astype(bool)

    bull_valid = (bull_low.notna() & ~bull_invalidated).fillna(False)
    bear_valid = (bear_high.notna() & ~bear_invalidated).fillna(False)
    return bull_valid, bear_valid


def trendline_breakout(df, lookback=2):
    """New Batch 3, Strategy 1 (HTF Trend Trendline Breakout) -- a genuinely
    NEW concept this codebase didn't have: connects the two most recently
    CONFIRMED swing lows (for a bullish break) or swing highs (for a
    bearish break) into a straight line, projects it forward bar-by-bar,
    and edge-triggers the first bar whose CLOSE crosses beyond that
    projected line -- the classic "internal/corrective trendline break as a
    trend-continuation entry" pattern.

    Own default (the source says "connect at least 2 swing points" with no
    mechanical rule for WHICH two): always the two MOST RECENT confirmed
    pivots of the relevant type, in chronological order -- the shortest-
    term, most current trendline a chart reader would actually draw, rather
    than searching further back for a "better fit" line (no mechanical
    definition of "better fit" is given, so none is invented here). A fresh
    pivot redraws the line immediately and clears any stale "already beyond
    the old line" state, so a break can only ever fire against the CURRENT
    two-point line, never a stale one.

    Deliberately a plain per-bar Python loop, same justification as
    valid_structure_trend()/sweep_invalidation_state() above: which two
    pivots are "the most recent" is genuinely sequential state that changes
    only at specific earlier bars, not a fixed rolling window. Zero
    look-ahead: a pivot only enters the state once swing_points() has
    already confirmed it (`lookback` bars after the fact, its real pivot
    bar), and the projected line is only ever evaluated at or after the
    bar its second anchor point was confirmed.

    Returns two boolean Series: bullish_break (close crosses above the
    ascending/descending lows-trendline), bearish_break (close crosses
    below the highs-trendline)."""
    swing_high, swing_low = swing_points(df, lookback)
    high = df["high"].values
    low = df["low"].values
    close = df["close"].values
    sh = swing_high.values
    sl = swing_low.values
    n = len(df)

    bullish = [False] * n
    bearish = [False] * n

    low_pivots = []   # [(bar_index, price), ...] chronological, max len 2
    high_pivots = []

    # Measured on real 60-90 day BTCUSDT 15m data: a stateful "was the LAST
    # bar under this same still-active 2-point line below it" check fired
    # ZERO times across tens of thousands of bars, at every lookback tried
    # (2/3/5/8). Root cause, confirmed by direct instrumentation: with
    # swing_points() this sensitive, any bar where price actually trades
    # below the current lows-line almost always gets confirmed as a BRAND
    # NEW (lower) swing low just `lookback` bars later -- which replaces
    # the pivot pair and resets the state before price can ever recover
    # back above the OLD line to complete a same-line cross. Real trendline
    # breaks in this style of data happen "the line gets redrawn slightly
    # steeper/shallower each time, and price is now on the other side of
    # wherever it CURRENTLY sits" rather than "the identical 2-point line
    # persists for many bars." So the cross is evaluated statelessly
    # against the CURRENT pivot pair's own line, comparing this bar to the
    # bar immediately before it (both extrapolated from the SAME two
    # anchors) -- no persistent flag, so a just-updated pivot pair doesn't
    # need any bar of "history" under itself before a cross can register.
    for i in range(n):
        if sl[i]:
            pivot_i = i - lookback
            low_pivots.append((pivot_i, low[pivot_i]))
            if len(low_pivots) > 2:
                low_pivots.pop(0)
        if sh[i]:
            pivot_i = i - lookback
            high_pivots.append((pivot_i, high[pivot_i]))
            if len(high_pivots) > 2:
                high_pivots.pop(0)

        if len(low_pivots) == 2 and i > 0:
            (i1, p1), (i2, p2) = low_pivots
            if i2 > i1 and i >= i2:
                slope = (p2 - p1) / (i2 - i1)
                line_now = p2 + slope * (i - i2)
                line_prev = p2 + slope * (i - 1 - i2)
                if close[i] > line_now and close[i - 1] <= line_prev:
                    bullish[i] = True

        if len(high_pivots) == 2 and i > 0:
            (i1, p1), (i2, p2) = high_pivots
            if i2 > i1 and i >= i2:
                slope = (p2 - p1) / (i2 - i1)
                line_now = p2 + slope * (i - i2)
                line_prev = p2 + slope * (i - 1 - i2)
                if close[i] < line_now and close[i - 1] >= line_prev:
                    bearish[i] = True

    return pd.Series(bullish, index=df.index), pd.Series(bearish, index=df.index)


def range_breakout_volume_confirm(df, range_bars=25, volume_avg_period=20,
                                   breakout_volume_mult=1.8, large_candle_atr_mult=1.5,
                                   atr_period=14):
    """New Batch 3, Strategy 2 (Range Breakout Volume Confirmation) -- a
    generic, non-proprietary equivalent (no branded/copyrighted indicator
    reproduced): detects a genuine consolidation (a trailing `range_bars`
    high/low band, own default 25 per the strategy's own "~25-30 candles"
    wording), a CLOSE beyond that band (not a wick), REQUIRES a real volume
    spike on the breakout candle relative to its own trailing average (a
    breakout with no volume behind it is treated as a fakeout and produces
    NO signal at all -- a hard filter, not a scoring adjustment), and
    classifies the breakout candle's size via an ATR-multiple threshold: a
    "standard" candle confirms on the VERY NEXT bar; a "very large" candle
    instead arms a retest -- the confirm only fires once price actually
    comes back to touch the broken level.

    Own defaults (source gives no exact numbers): breakout_volume_mult=1.8
    for "a CLEAR volume spike" -- deliberately stricter than the existing
    plain "volume" concept's own 1.5x default (volume_filter()), since this
    is explicitly a hard fakeout filter, not a soft quality signal.
    large_candle_atr_mult=1.5x ATR(14) for "very large" -- the same
    large-candle threshold already used elsewhere in this codebase (e.g.
    consolidation_impulse_zones' impulse_atr_mult default). A retest that
    never arrives is abandoned once price closes back fully through the
    ORIGINAL opposite side of the range -- own default for "this breakout
    failed, nothing left to retest."

    Deliberately a plain per-bar Python loop (like valid_structure_trend
    and sweep_invalidation_state above): whether THIS bar is "the very next
    candle after a standard breakout" or "a retest of a level broken
    several bars ago" is genuinely sequential state, not a vectorized
    rolling-window check. Zero look-ahead: the range/volume rolling windows
    are shifted by 1 (always "before this bar," never including it), and a
    freshly-resolved bar's OWN state change is never re-evaluated for a
    brand-new breakout within that same bar (a resolution and a fresh
    detection never both happen at bar i).

    Returns two boolean Series: bull_confirm, bear_confirm -- the exact bar
    an entry should fire, already carrying both the volume-fakeout filter
    and the standard/retest branching."""
    high = df["high"].values
    low = df["low"].values
    close = df["close"].values
    volume = df["volume"].values
    n = len(df)

    atr_vals = atr(df, atr_period).values
    # Both rolling stats end at the bar BEFORE the one being classified --
    # "the range/volume seen so far," never including the candle itself.
    range_high_s = pd.Series(high).rolling(range_bars).max().shift(1).values
    range_low_s = pd.Series(low).rolling(range_bars).min().shift(1).values
    avg_volume_s = pd.Series(volume).rolling(volume_avg_period).mean().shift(1).values

    bull_confirm = [False] * n
    bear_confirm = [False] * n
    # sl_ref_*: the breakout/breakdown candle's OWN opposite extreme (its
    # low for a bull setup, high for a bear setup) -- "stop-loss ... or the
    # extreme of the breakout/breakdown candle" -- carried from the
    # breakout bar to whichever later bar actually confirms the entry, so
    # ConfiguredStrategy can read a real stop-loss reference at the exact
    # signal bar without re-deriving which candle the breakout happened on.
    sl_ref_bull = [None] * n
    sl_ref_bear = [None] * n

    mode = None            # None | "next_bar_bull" | "next_bar_bear" | "retest_bull" | "retest_bear"
    retest_level = None    # the broken range boundary a retest must touch
    abandon_level = None   # the OPPOSITE boundary -- closing back beyond this cancels the setup
    pending_sl_ref = None  # the breakout candle's own opposite extreme, held until confirm fires

    for i in range(n):
        if mode == "next_bar_bull":
            bull_confirm[i] = True
            sl_ref_bull[i] = pending_sl_ref
            mode = None
            continue
        if mode == "next_bar_bear":
            bear_confirm[i] = True
            sl_ref_bear[i] = pending_sl_ref
            mode = None
            continue
        if mode == "retest_bull":
            if low[i] <= retest_level <= high[i]:
                bull_confirm[i] = True
                sl_ref_bull[i] = pending_sl_ref
                mode = None
            elif close[i] < abandon_level:
                mode = None
            continue
        if mode == "retest_bear":
            if low[i] <= retest_level <= high[i]:
                bear_confirm[i] = True
                sl_ref_bear[i] = pending_sl_ref
                mode = None
            elif close[i] > abandon_level:
                mode = None
            continue

        # Only reached when mode was already None at the START of this bar
        # -- a bar that just resolved a pending confirm never ALSO opens a
        # fresh detection window on itself.
        rh, rl, av, cur_atr = range_high_s[i], range_low_s[i], avg_volume_s[i], atr_vals[i]
        if rh == rh and rl == rl and av == av:  # NaN guards -- windows not yet full
            has_volume_spike = volume[i] > av * breakout_volume_mult
            candle_range = high[i] - low[i]
            is_large = (cur_atr == cur_atr) and candle_range >= large_candle_atr_mult * cur_atr

            if close[i] > rh and has_volume_spike:
                if is_large:
                    mode, retest_level, abandon_level = "retest_bull", rh, rl
                else:
                    mode = "next_bar_bull"
                pending_sl_ref = low[i]
            elif close[i] < rl and has_volume_spike:
                if is_large:
                    mode, retest_level, abandon_level = "retest_bear", rl, rh
                else:
                    mode = "next_bar_bear"
                pending_sl_ref = high[i]

    return (pd.Series(bull_confirm, index=df.index), pd.Series(bear_confirm, index=df.index),
            pd.Series(sl_ref_bull, index=df.index, dtype=float), pd.Series(sl_ref_bear, index=df.index, dtype=float))


# ------------------------------------------------------ New Batch 4 concepts

def heikin_ashi(df):
    """Standard Heikin Ashi smoothed-candle recalculation -- a well-known,
    non-proprietary charting technique (not a branded/copyrighted
    indicator). ha_close = OHLC4; ha_open = midpoint of the PREVIOUS HA
    candle's own open/close (first bar seeds from the real candle's own
    open/close -- the standard convention, since there is no prior HA
    candle yet); ha_high/ha_low extend to also include the real bar's own
    high/low. Inherently sequential (each ha_open depends on the previous
    bar's ha_open/ha_close), so this is a per-bar loop rather than
    vectorized -- same style as trendline_breakout/
    range_breakout_volume_confirm above. Returns four Series:
    ha_open, ha_high, ha_low, ha_close."""
    o, h, l, c = df["open"].values, df["high"].values, df["low"].values, df["close"].values
    n = len(df)
    ha_open = np.empty(n)
    ha_close = (o + h + l + c) / 4.0
    ha_high = np.empty(n)
    ha_low = np.empty(n)
    for i in range(n):
        if i == 0:
            ha_open[i] = (o[i] + c[i]) / 2.0
        else:
            ha_open[i] = (ha_open[i - 1] + ha_close[i - 1]) / 2.0
        ha_high[i] = max(h[i], ha_open[i], ha_close[i])
        ha_low[i] = min(l[i], ha_open[i], ha_close[i])
    return (pd.Series(ha_open, index=df.index), pd.Series(ha_high, index=df.index),
            pd.Series(ha_low, index=df.index), pd.Series(ha_close, index=df.index))


def fibonacci_retracement_zone(df, lookback=2):
    """Fibonacci retracement levels (38.2/61.8/50%) for the most recent
    alternating swing leg -- reuses swing_points()/support_resistance()
    directly, no new pivot logic. direction="up" when the most recently
    confirmed swing event was a HIGH following an earlier LOW (the
    source's "swing-low-to-swing-high draw" for an uptrend); "down"
    mirrors it (swing-high-to-swing-low). The leg's own start/end anchor
    prices are just the current support/resistance values (already causal,
    ffill'd) -- support_resistance()'s ffill guarantees whichever of the
    two updated most recently is the "end" of the active leg, so no extra
    per-bar loop is needed. Returns (fib_618, fib_50, fib_382, direction)
    as per-bar Series -- the 0%/100% levels are just support/resistance
    themselves, not separately returned. NOTE: for an "up" leg, prices sit
    low < fib_618 < fib_50 < fib_382 < high (a deeper retracement is a
    LOWER price); for a "down" leg the same three levels sit in the
    mirrored order low < fib_382 < fib_50 < fib_618 < high (a deeper
    retracement is a HIGHER price) -- both are the standard convention."""
    swing_high, swing_low = swing_points(df, lookback)
    support, resistance = support_resistance(df, lookback)

    last_event = pd.Series(
        np.where(swing_high.values, "high", np.where(swing_low.values, "low", None)),
        index=df.index,
    ).ffill()
    direction = last_event.map({"high": "up", "low": "down"})

    is_up = (direction == "up").values
    leg_high = resistance.values
    leg_low = support.values
    rng = leg_high - leg_low

    fib_382 = np.where(is_up, leg_high - 0.382 * rng, leg_low + 0.382 * rng)
    fib_50 = np.where(is_up, leg_high - 0.5 * rng, leg_low + 0.5 * rng)
    fib_618 = np.where(is_up, leg_high - 0.618 * rng, leg_low + 0.618 * rng)

    return (pd.Series(fib_618, index=df.index), pd.Series(fib_50, index=df.index),
            pd.Series(fib_382, index=df.index), direction)


def fixed_range_volume_profile(df, lookback=2, bins=24, min_bars=5):
    """Fixed Range Volume Profile (FRVP) Point of Control -- volume-at-price
    profile computed over the range between the two most recent
    ALTERNATING confirmed swing points (swing_points()), re-drawn every
    time a new swing point confirms. Deliberately NOT a fixed calendar
    window like volume_profile_previous_day() -- this is the "plot from
    swing-low to swing-high" construction the source describes. Direction
    follows naturally from which swing came last: swing-low then
    swing-high = up-leg (per the source's "uptrend: low-to-high"); the
    mirror is a down-leg. A leg shorter than `min_bars` is skipped (too few
    candles for a meaningful profile) -- the previous leg's POC keeps
    carrying forward until a genuinely usable new leg confirms. Deliberately
    a per-bar Python loop (like heikin_ashi/trendline_breakout above): the
    active range's start/end bar index changes only at discrete swing
    events, not something a rolling window expresses. Zero look-ahead: a
    leg's profile is only computed once BOTH its endpoints are already
    confirmed swing points, and only ever uses bars up to and including the
    bar where that confirmation became known. Returns (poc, direction) as
    two per-bar Series."""
    swing_high, swing_low = swing_points(df, lookback)
    high, low = df["high"].values, df["low"].values
    close, volume = df["close"].values, df["volume"].values
    sh, sl = swing_high.values, swing_low.values
    n = len(df)

    poc = np.full(n, np.nan)
    direction = np.array([None] * n, dtype=object)

    last_low_i = last_high_i = None
    range_dir = None
    cached_poc = None

    for i in range(n):
        new_leg = False
        leg_start_i = leg_end_i = None
        if sl[i]:
            last_low_i = i
            if last_high_i is not None and last_high_i < last_low_i:
                leg_start_i, leg_end_i, this_dir = last_high_i, last_low_i, "down"
                new_leg = True
        if sh[i]:
            last_high_i = i
            if last_low_i is not None and last_low_i < last_high_i:
                leg_start_i, leg_end_i, this_dir = last_low_i, last_high_i, "up"
                new_leg = True
        if new_leg and (leg_end_i - leg_start_i) >= min_bars:
            seg_high = high[leg_start_i:leg_end_i + 1]
            seg_low = low[leg_start_i:leg_end_i + 1]
            seg_close = close[leg_start_i:leg_end_i + 1]
            seg_vol = volume[leg_start_i:leg_end_i + 1]
            lo, hi = seg_low.min(), seg_high.max()
            if hi > lo and seg_vol.sum() > 0:
                edges = np.linspace(lo, hi, bins + 1)
                bucket_idx = np.clip(np.digitize(seg_close, edges) - 1, 0, bins - 1)
                bucket_volume = np.zeros(bins)
                np.add.at(bucket_volume, bucket_idx, seg_vol)
                centers = (edges[:-1] + edges[1:]) / 2
                poc_i = int(np.argmax(bucket_volume))
                cached_poc = centers[poc_i]
                range_dir = this_dir
        poc[i] = cached_poc if cached_poc is not None else np.nan
        direction[i] = range_dir

    return pd.Series(poc, index=df.index), pd.Series(direction, index=df.index)


def frvp_market_shape(df, lookback=2, bins=24, min_bars=5, value_area_pct=0.70,
                       low_node_frac=0.25, high_node_frac=1.5):
    """New Batch 5, Strategy 2 (Fixed Range Volume Profile): the richer
    profile fixed_range_volume_profile() above deliberately doesn't compute
    -- Value Area High/Low, High/Low Volume Node ZONES (not just a POC
    point), and a Market Shape classification (D/P/b/Thin/Capital-B),
    anchored to the same swing-to-swing leg construction as
    fixed_range_volume_profile() (re-drawn every time a new leg confirms; a
    leg shorter than min_bars is skipped and the previous leg's profile
    carries forward -- identical anchoring rules, so the two functions never
    disagree about WHICH leg is active).

    Shape classification is a real, testable measure (the source itself
    calls this subjective and asks for one) -- builder default, documented
    here since nothing in the source gives an exact number:
      - "thin": no bucket exceeds high_node_frac x the leg's average bucket
        volume at all -- no real high-volume node exists anywhere.
      - "capital_b": 2+ SEPARATED high-volume-node clusters (a valley of
        normal/low volume between them) -- a genuine double distribution.
      - "p": otherwise, >= 65% of the leg's total volume sits above the
        leg's own 50% price midpoint (aggressive buyers pushed price up
        through most of the volume).
      - "b": otherwise, >= 65% of the leg's total volume sits BELOW the 50%
        midpoint (mirror of "p").
      - "d": otherwise (volume roughly balanced around the midpoint).
    high_node_frac/low_node_frac reuse volume_nodes_previous_day()'s own
    already-established thresholds (1.5x / 0.25x average bucket volume) for
    consistency across the codebase rather than inventing new ones.

    hvn_low_zone/hvn_high_zone: the lower-priced and higher-priced
    high-volume-node cluster (by price, not by rank) -- for p/b/d shapes
    (a single HVN cluster) these are the SAME zone, used as support (long
    setups) or resistance (short setups) depending on the shape; for
    capital_b they are genuinely the two distinct zones the source
    describes ("both HVNs act as separate support/resistance levels").
    lvn_zone: the single most prominent (widest) low-volume-node cluster in
    the leg -- own default for "which LVN" when several exist, since price
    most naturally makes its fast move through the LVN immediately
    surrounding the dominant high-volume node it is leaving.

    p_shape_invalidated: per the source's own explicit rule, True from the
    first bar price closes below the leg's 50% midpoint onward, for the
    remainder of a leg classified "p" (that shape's long setup should no
    longer be trusted once this flips True).

    Returns (poc, vah, val, shape, hvn_low_zone_lo, hvn_low_zone_hi,
    hvn_high_zone_lo, hvn_high_zone_hi, lvn_zone_lo, lvn_zone_hi,
    p_shape_invalidated) -- eleven per-bar Series, same zero-look-ahead
    causal guarantee as fixed_range_volume_profile()."""
    swing_high, swing_low = swing_points(df, lookback)
    high, low = df["high"].values, df["low"].values
    close, volume = df["close"].values, df["volume"].values
    sh, sl = swing_high.values, swing_low.values
    n = len(df)

    poc = np.full(n, np.nan)
    vah = np.full(n, np.nan)
    val = np.full(n, np.nan)
    shape = np.array([None] * n, dtype=object)
    hvn_lo_lo = np.full(n, np.nan)
    hvn_lo_hi = np.full(n, np.nan)
    hvn_hi_lo = np.full(n, np.nan)
    hvn_hi_hi = np.full(n, np.nan)
    lvn_lo = np.full(n, np.nan)
    lvn_hi = np.full(n, np.nan)
    p_invalid = np.full(n, False)

    last_low_i = last_high_i = None
    cached = None  # tuple of the 10 scalar values above, held until the next usable leg
    p_leg_active = False
    p_invalid_state = False

    def _clusters(idx_array):
        if len(idx_array) == 0:
            return []
        groups = np.split(idx_array, np.where(np.diff(idx_array) != 1)[0] + 1)
        return [tuple(g) for g in groups]

    for i in range(n):
        new_leg = False
        leg_start_i = leg_end_i = None
        if sl[i]:
            last_low_i = i
            if last_high_i is not None and last_high_i < last_low_i:
                leg_start_i, leg_end_i = last_high_i, last_low_i
                new_leg = True
        if sh[i]:
            last_high_i = i
            if last_low_i is not None and last_low_i < last_high_i:
                leg_start_i, leg_end_i = last_low_i, last_high_i
                new_leg = True

        if new_leg and (leg_end_i - leg_start_i) >= min_bars:
            seg_high = high[leg_start_i:leg_end_i + 1]
            seg_low = low[leg_start_i:leg_end_i + 1]
            seg_close = close[leg_start_i:leg_end_i + 1]
            seg_vol = volume[leg_start_i:leg_end_i + 1]
            lo, hi = seg_low.min(), seg_high.max()
            if hi > lo and seg_vol.sum() > 0:
                edges = np.linspace(lo, hi, bins + 1)
                centers = (edges[:-1] + edges[1:]) / 2
                bucket_idx = np.clip(np.digitize(seg_close, edges) - 1, 0, bins - 1)
                bucket_volume = np.zeros(bins)
                np.add.at(bucket_volume, bucket_idx, seg_vol)
                total = bucket_volume.sum()

                poc_i = int(np.argmax(bucket_volume))
                leg_poc = centers[poc_i]

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
                leg_vah, leg_val = edges[hi_i + 1], edges[lo_i]

                avg = bucket_volume.mean()
                mid_price = (lo + hi) / 2.0
                upper_frac = bucket_volume[centers > mid_price].sum() / total if total > 0 else 0.0

                hvn_clusters = _clusters(np.where(bucket_volume > high_node_frac * avg)[0]) if avg > 0 else []
                lvn_clusters = _clusters(np.where(bucket_volume < low_node_frac * avg)[0]) if avg > 0 else []

                if not hvn_clusters:
                    leg_shape = "thin"
                elif len(hvn_clusters) >= 2:
                    leg_shape = "capital_b"
                elif upper_frac >= 0.65:
                    leg_shape = "p"
                elif upper_frac <= 0.35:
                    leg_shape = "b"
                else:
                    leg_shape = "d"

                if hvn_clusters:
                    # Rank clusters by their OWN total volume (which HVN is
                    # "the" dominant one for p/b/d's single-zone case), then
                    # re-order the top two by PRICE for capital_b's
                    # low-zone/high-zone semantics.
                    ranked = sorted(hvn_clusters, key=lambda c: bucket_volume[list(c)].sum(), reverse=True)
                    top_two = ranked[:2]
                    top_two_by_price = sorted(top_two, key=lambda c: c[0])
                    low_cluster = top_two_by_price[0]
                    high_cluster = top_two_by_price[-1]
                    leg_hvn_lo_lo, leg_hvn_lo_hi = edges[low_cluster[0]], edges[low_cluster[-1] + 1]
                    leg_hvn_hi_lo, leg_hvn_hi_hi = edges[high_cluster[0]], edges[high_cluster[-1] + 1]
                else:
                    leg_hvn_lo_lo = leg_hvn_lo_hi = leg_hvn_hi_lo = leg_hvn_hi_hi = np.nan

                if lvn_clusters:
                    widest = max(lvn_clusters, key=len)
                    leg_lvn_lo, leg_lvn_hi = edges[widest[0]], edges[widest[-1] + 1]
                else:
                    leg_lvn_lo = leg_lvn_hi = np.nan

                cached = (leg_poc, leg_vah, leg_val, leg_shape,
                          leg_hvn_lo_lo, leg_hvn_lo_hi, leg_hvn_hi_lo, leg_hvn_hi_hi,
                          leg_lvn_lo, leg_lvn_hi, mid_price)
                p_leg_active = (leg_shape == "p")
                p_invalid_state = False

        if cached is not None:
            (poc[i], vah[i], val[i], shape[i],
             hvn_lo_lo[i], hvn_lo_hi[i], hvn_hi_lo[i], hvn_hi_hi[i],
             lvn_lo[i], lvn_hi[i], leg_mid) = cached
            if p_leg_active and not p_invalid_state and close[i] < leg_mid:
                p_invalid_state = True
        p_invalid[i] = p_invalid_state

    idx = df.index
    return (pd.Series(poc, index=idx), pd.Series(vah, index=idx), pd.Series(val, index=idx),
            pd.Series(shape, index=idx), pd.Series(hvn_lo_lo, index=idx), pd.Series(hvn_lo_hi, index=idx),
            pd.Series(hvn_hi_lo, index=idx), pd.Series(hvn_hi_hi, index=idx),
            pd.Series(lvn_lo, index=idx), pd.Series(lvn_hi, index=idx),
            pd.Series(p_invalid, index=idx))


def long_wick_candle(df, wick_frac=0.5):
    """New Batch 5, Strategies 3 & 7: the generic "long wick candle" =
    liquidity-sweep/rejection signal both strategies' own source documents
    describe -- a candle whose LOWER (bullish rejection) or UPPER (bearish
    rejection) wick alone is at least wick_frac of the candle's own full
    high-low range. Deliberately body-size-agnostic (unlike pin_bar(),
    which ALSO requires a small body relative to the wick) -- exactly the
    source's own "long wick" wording, nothing more. wick_frac=0.5 is this
    batch's own documented default (neither source gives an exact number),
    used consistently by both strategies rather than each inventing its
    own. Returns (bull_long_wick, bear_long_wick)."""
    high, low, close, open_ = df["high"], df["low"], df["close"], df["open"]
    rng = (high - low).replace(0, np.nan)
    body_top = pd.concat([open_, close], axis=1).max(axis=1)
    body_bottom = pd.concat([open_, close], axis=1).min(axis=1)
    lower_wick = body_bottom - low
    upper_wick = high - body_top
    bull_long_wick = ((lower_wick / rng) >= wick_frac).fillna(False)
    bear_long_wick = ((upper_wick / rng) >= wick_frac).fillna(False)
    return bull_long_wick, bear_long_wick


def nth_touch_of_level(touch_event, level_series, n=3):
    """New Batch 5, Strategy 3: True from the Nth time `touch_event` fires
    against the CURRENT value of `level_series` onward (>= n, not exactly
    n -- the source's own "the 3rd or 4th time" already reads as a loose
    "by the time it's been tested a few times", not one exact bar) --
    "wait for price to enter the zone for the 3rd or 4th time" before a
    setup counts. Generalizes first_signal_per_level()'s "retire the count
    when the level itself changes" idea (that function is the n=1 special
    case, restated as a boolean already-used flag instead of a running
    count) to a genuine per-level touch counter."""
    touch = touch_event.fillna(False).to_numpy()
    levels = level_series.to_numpy()
    n_bars = len(touch)
    out = [False] * n_bars
    current_level = None
    count = 0
    for i in range(n_bars):
        lvl = levels[i]
        if lvl is None or (isinstance(lvl, float) and np.isnan(lvl)):
            continue
        if lvl != current_level:
            current_level = lvl
            count = 0
        if touch[i]:
            count += 1
            if count >= n:
                out[i] = True
    return pd.Series(out, index=touch_event.index, dtype=bool)


def ichimoku_cloud(df, conversion_period=9, base_period=26, span_b_period=52, displacement=26):
    """New Batch 5, Strategy 9: standard Ichimoku Kinko Hyo -- a
    well-defined, publicly documented, non-proprietary indicator, genuinely
    new to this codebase. Conversion Line = (9-period high + 9-period
    low)/2. Base Line = (26-period high + 26-period low)/2. Leading Span A
    = (Conversion+Base)/2, Leading Span B = (52-period high + 52-period
    low)/2, BOTH plotted `displacement` (26) candles AHEAD -- i.e. the
    cloud edge visible at bar i was computed from data as of bar
    i-displacement, then carried forward; `.shift(displacement)` (a
    positive shift, pulling PAST rows into the current one) is exactly
    this, with zero look-ahead.

    Lagging Span is NOT returned as a plotted line (that would need a
    genuine negative shift -- today's close plotted `displacement` bars
    BACK on the chart -- which has no causal, no-look-ahead reading when
    evaluated for a live trading decision at bar i). What IS causally
    checkable at bar i is exactly what "Lagging Span is above/below the
    price candles" means for a trading decision made TODAY: is the
    CURRENT close above/below the close from `displacement` bars ago (the
    level today's lagging span value would sit against on the chart)?
    That comparison uses only past+current data, so it's returned directly
    as (lagging_above_price, lagging_below_price) booleans instead of a
    plotted line.

    Returns (conversion, base, span_a, span_b, lagging_above_price,
    lagging_below_price)."""
    high, low, close = df["high"], df["low"], df["close"]
    conversion = (high.rolling(conversion_period).max() + low.rolling(conversion_period).min()) / 2.0
    base = (high.rolling(base_period).max() + low.rolling(base_period).min()) / 2.0
    span_a = ((conversion + base) / 2.0).shift(displacement)
    span_b = ((high.rolling(span_b_period).max() + low.rolling(span_b_period).min()) / 2.0).shift(displacement)
    lagging_above_price = (close > close.shift(displacement)).fillna(False)
    lagging_below_price = (close < close.shift(displacement)).fillna(False)
    return conversion, base, span_a, span_b, lagging_above_price, lagging_below_price


def lwti(df, period=25, smoothing=20):
    """LWTI (Linear Weighted Trend Indicator) -- New Batch 4, Strategy 5.
    A standard, publicly-documented (non-proprietary/non-branded) momentum
    oscillator, but multiple slightly different community implementations
    exist and the source gives no exact formula matching its own "+50/-50"
    banding -- this is ONE deterministic, reasonable reconstruction,
    explicitly flagged as a builder default rather than a byte-exact
    reproduction of any specific published script: a linear-weighted-
    moving-average's own momentum (this bar's WMA minus the previous bar's),
    normalized against its OWN recent rolling volatility (not ATR -- a
    25-period WMA's bar-to-bar change is naturally much smaller than the raw
    ATR, which measured against real data made +/-100 essentially
    unreachable, only 0.03% of bars) so that 1 std dev of recent momentum
    maps to +/-50 and 2 std devs caps at +/-100 -- a genuinely reachable,
    meaningful band -- then smoothed with an EMA. Returns one Series."""
    weights = np.arange(1, period + 1, dtype=float)
    wma = df["close"].rolling(period).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)
    momentum = wma - wma.shift(1)
    rolling_std = momentum.rolling(period).std().replace(0, np.nan)
    normalized = (momentum / rolling_std).clip(-2, 2) * 50
    return normalized.ewm(span=smoothing, adjust=False).mean()
