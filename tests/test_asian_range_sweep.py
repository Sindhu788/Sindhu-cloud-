"""Asian Range London Sweep needs a "most recently CLOSED session's
range" (session_high_low() only gives the CURRENT, still-forming session)
plus the sweep-then-reclaim sequence, day-scoped like four_hour_range's."""

import pandas as pd

from backtest_engine import concepts
from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from backtest_engine.configured_strategy import ConfiguredStrategy


def _utc_df(rows, start="2026-01-05 00:00", freq="5min"):
    idx = pd.date_range(start, periods=len(rows), freq=freq, tz="UTC")
    return pd.DataFrame({
        "open": [r[0] for r in rows], "high": [r[1] for r in rows],
        "low": [r[2] for r in rows], "close": [r[3] for r in rows],
    }, index=idx)


def test_previous_session_high_low_holds_asian_range_through_london():
    # 00:00-08:00 UTC = asian (96 bars * 5min = 480min = 8h)
    rows = [(100.0, 101.0, 99.0, 100.0) for _ in range(96)]
    # 08:00 onward = london -- asian range should now read [99, 101], held constant
    rows += [(100.0, 100.5, 99.5, 100.0) for _ in range(10)]
    df = _utc_df(rows)
    prev_high, prev_low = concepts.previous_session_high_low(df, "asian")
    assert prev_high.iloc[100] == 101.0
    assert prev_low.iloc[100] == 99.0


def test_session_sweep_reclaim_fires_edge_triggered_after_sweep():
    rows = [(100.0, 101.0, 99.0, 100.0) for _ in range(96)]  # asian range [99, 101]
    rows.append((100.0, 100.2, 95.0, 95.5))   # london bar: sweeps below 99
    rows.append((95.5, 96.0, 94.5, 95.8))     # still outside
    rows.append((95.8, 100.5, 95.0, 100.2))   # closes back above 99 -> reclaim
    df = _utc_df(rows)
    bull_sweep, bear_sweep, bull_reclaim, bear_reclaim = concepts.session_sweep_reclaim(df, "asian")
    assert bull_sweep.iloc[96] == True
    assert bull_reclaim.iloc[98] == True
    assert bull_reclaim.iloc[97] == False  # not yet reclaimed


def test_asian_range_sweep_reclaim_concept_enforces_day_scoped_order():
    """End-to-end wiring + the exact 'right events, wrong day' rejection
    this task's standard requires (same standard as 4-Hour Range)."""
    rows = [(100.0, 101.0, 99.0, 100.0) for _ in range(96)]   # day 1 asian range [99,101]
    rows.append((100.0, 100.2, 95.0, 95.5))                    # day 1 london: sweep below, NO reclaim before day ends
    rows += [(95.5, 96.0, 94.5, 95.0) for _ in range(200)]     # day 1 stays outside, day ends
    rows += [(97.0, 98.0, 96.0, 97.0) for _ in range(96)]      # day 2 asian range [96,98] (unrelated)
    rows.append((97.0, 98.5, 96.5, 98.2))                      # day 2 london bar -- close inside day-2's OWN range,
                                                                 # must NOT be treated as day-1's reclaim
    df = _utc_df(rows)

    cfg = StrategyConfig(
        name="asian range sweep wiring test",
        timeframes={"entry": "5m"},
        concepts_used=["asian_range_sweep_reclaim"],
        long_entry_conditions=[Condition(type="concept", name="asian_range_sweep_reclaim",
                                          direction="bullish", lookback_bars=1)],
        stop_loss=SLTPSpec(type="signal_candle", value=1.0),
        take_profit=SLTPSpec(type="rr", value=2.0),
        risk_pct=1.0,
    )
    strat = ConfiguredStrategy(cfg)
    ConfiguredStrategy._compute_concept_columns(df, {"asian_range_sweep_reclaim"})
    assert not df["asian_long_confirm"].any(), "day-1 sweep incorrectly paired with a day-2 event"
