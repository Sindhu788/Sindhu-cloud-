"""4-Hour Range Breakout-Retest needs two things not previously built:

1. A New-York-timezone-aware "first N minutes of the day" window
   (concepts.four_hour_range() / four_hour_range_breakout()) -- the
   existing opening_range()/_first_window_range() family is UTC-anchored
   only, which would mark the wrong "first candle of the day" for a
   strategy that explicitly requires NY time.
2. A day-boundary-aware sequential_event() (reset_key param): the
   breakout-then-re-entry order must be enforced WITHIN the same trading
   day -- an evening breakout with no same-day re-entry must not pair with
   a coincidental inside-range close on a LATER day.
"""

import pandas as pd

from backtest_engine import concepts
from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from backtest_engine.configured_strategy import ConfiguredStrategy


def _tz_df(rows, start="2026-01-01 00:00", freq="5min", tz="America/New_York"):
    idx = pd.date_range(start, periods=len(rows), freq=freq, tz=tz).tz_convert("UTC")
    return pd.DataFrame({
        "open": [r[0] for r in rows], "high": [r[1] for r in rows],
        "low": [r[2] for r in rows], "close": [r[3] for r in rows],
    }, index=idx)


# --------------------------------------------------------------- sequential_event reset_key

def test_reset_key_blocks_cross_day_pairing():
    # event_a fires on "day 1", event_b fires on "day 2" -- must NOT pair.
    event_a = pd.Series([False, True, False, False])
    event_b = pd.Series([False, False, False, True])
    day_key = pd.Series(["day1", "day1", "day2", "day2"])
    result = concepts.sequential_event(event_a, event_b, reset_key=day_key)
    assert not result.any()


def test_reset_key_allows_same_day_pairing():
    event_a = pd.Series([False, True, False, False])
    event_b = pd.Series([False, False, False, True])
    day_key = pd.Series(["day1", "day1", "day1", "day1"])
    result = concepts.sequential_event(event_a, event_b, reset_key=day_key)
    assert list(result) == [False, False, False, True]


def test_no_reset_key_behaves_exactly_as_before():
    """Backward compatibility: CRT 2.0 / CHoCH never pass reset_key --
    their existing behavior (no day-boundary awareness) must be
    byte-for-byte unchanged."""
    event_a = pd.Series([False, True, False, False])
    event_b = pd.Series([False, False, False, True])
    result = concepts.sequential_event(event_a, event_b)
    assert list(result) == [False, False, False, True]


# --------------------------------------------------------------- four_hour_range (NY tz)

def test_four_hour_range_marks_first_4h_candle_in_ny_time():
    # 00:00-04:00 NY = the "first 4h candle" window; a bar at 04:05 NY is
    # already outside it, and the range should hold that first window's
    # high/low.
    rows = []
    for i in range(60):  # 60 bars * 5min = 5 hours of NY-local time
        rows.append((100 + i * 0.1, 101 + i * 0.1, 99 + i * 0.1, 100 + i * 0.1))
    df = _tz_df(rows)
    range_high, range_low = concepts.four_hour_range(df)
    # bars 0..47 are within the first 240 minutes (48 bars * 5min = 240min)
    expected_high = df["high"].iloc[:48].max()
    expected_low = df["low"].iloc[:48].min()
    assert range_high.iloc[-1] == expected_high
    assert range_low.iloc[-1] == expected_low


def test_four_hour_range_breakout_requires_full_close_not_wick():
    rows = []
    for i in range(48):
        rows.append((100.0, 101.0, 99.0, 100.0))
    # bar 48 (right after the window closes): a big wick above the range
    # but close stays INSIDE -- must NOT count as a breakout.
    rows.append((100.0, 110.0, 99.0, 100.5))
    # bar 49: a real close beyond the range high (101.0).
    rows.append((100.5, 106.0, 100.0, 105.0))
    df = _tz_df(rows)
    bull_break, bear_break = concepts.four_hour_range_breakout(df)
    assert bull_break.iloc[48] == False  # wick-only, no close beyond range
    assert bull_break.iloc[49] == True   # real close beyond range


# --------------------------------------------------------------- end-to-end wiring + sequence order

def test_four_hour_range_reentry_concept_fires_in_correct_order():
    """Full pipeline: breakout (close outside range) THEN re-entry (close
    back inside), strictly in that order, produces a real "long_confirm"/
    "short_confirm" firing via the actual ConfiguredStrategy path."""
    rows = []
    for i in range(48):
        rows.append((100.0, 101.0, 99.0, 100.0))  # forms the 4h range: [99, 101]
    rows.append((100.0, 100.5, 90.0, 90.0))    # bar 48: close BELOW range (breakout down)
    rows.append((90.0, 92.0, 89.0, 91.0))      # bar 49: still outside
    rows.append((91.0, 100.5, 90.5, 100.0))    # bar 50: closes back INSIDE range -> long confirm
    df = _tz_df(rows)

    cfg = StrategyConfig(
        name="4h range reentry wiring test",
        timeframes={"entry": "5m"},
        concepts_used=["four_hour_range_reentry"],
        long_entry_conditions=[Condition(type="concept", name="four_hour_range_reentry",
                                          direction="bullish", lookback_bars=1)],
        stop_loss=SLTPSpec(type="signal_candle", value=1.0),
        take_profit=SLTPSpec(type="rr", value=2.0),
        risk_pct=1.0,
    )
    strat = ConfiguredStrategy(cfg)
    ConfiguredStrategy._compute_concept_columns(df, {"four_hour_range_reentry"})
    merged = df.add_prefix("entry_")
    cond = cfg.long_entry_conditions[0]
    results = [strat._eval(cond, merged, i) for i in range(len(merged))]
    assert results[50] is True
    assert results[49] is False
    assert results[48] is False


def test_breakout_with_no_same_day_reentry_never_confirms_next_day():
    """The exact 'right events, wrong order/day' rejection this task asks
    to prove: a breakout late on day 1 with NO same-day re-entry, followed
    by an UNRELATED inside-range close on day 2 (after day 2's own new
    range forms), must NOT be treated as a valid re-entry of day 1's
    breakout."""
    rows = []
    # Day 1: form range, then break out with no re-entry before day ends.
    for i in range(48):
        rows.append((100.0, 101.0, 99.0, 100.0))
    rows.append((100.0, 100.5, 90.0, 90.0))  # day 1 breakout down, bar 48
    for i in range(240):
        rows.append((90.0, 91.0, 89.0, 90.0))  # day 1 stays outside range until day ends (288 bars/day = 24h * 12 bars/hr)
    # Day 2 begins (bar 288 = 24h later): forms its OWN new range, unrelated to day 1's breakout.
    for i in range(48):
        rows.append((95.0, 96.0, 94.0, 95.0))
    # Day 2, bar after its own window closes: a close "inside" day-2's range purely by
    # coincidence -- must not be treated as day-1's re-entry.
    rows.append((95.0, 95.5, 94.5, 95.2))
    df = _tz_df(rows)

    ConfiguredStrategy._compute_concept_columns(df, {"four_hour_range_reentry"})
    assert not df["range_long_confirm"].any(), "day-1 breakout incorrectly paired with a day-2 event"
