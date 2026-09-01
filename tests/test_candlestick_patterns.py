"""Candlestick Pattern Reversal Strategy needs two genuinely new pieces:
1. concepts.doji_pattern() / concepts.morning_evening_star() -- new pattern
   detectors (Hammer/Shooting Star reuse the EXISTING pin_bar(); Engulfing
   reuses the existing engulfing_candle()/"engulfing" concept, no new code).
2. concepts.candle_pattern_confirmation() -- "pattern fires, THEN a later
   candle confirms by closing beyond the PATTERN candle's own extreme,"
   sequence-ordered via concepts.sequential_event().

Also verifies the "structure" stop-loss type's new optional buffer
(spec.value, previously unused by that type) stays a no-op for every
existing strategy while giving Candlestick Pattern Reversal a real margin.
"""

import pandas as pd

from backtest_engine import concepts
from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from backtest_engine.configured_strategy import ConfiguredStrategy


def _df(rows):
    idx = pd.date_range("2026-01-01", periods=len(rows), freq="1h", tz="UTC")
    return pd.DataFrame({
        "open": [r[0] for r in rows], "high": [r[1] for r in rows],
        "low": [r[2] for r in rows], "close": [r[3] for r in rows],
    }, index=idx)


def test_doji_pattern_detects_small_body_only():
    rows = [
        (100, 110, 90, 100.5),   # body=0.5, range=20 -> 2.5% -> doji
        (100, 110, 90, 109),     # body=9, range=20 -> 45% -> not doji
    ]
    df = _df(rows)
    doji = concepts.doji_pattern(df, max_body_pct=10.0)
    assert list(doji) == [True, False]


def test_morning_star_detects_three_candle_sequence():
    rows = [
        (110, 111, 95, 96),      # large red
        (96, 97, 94, 96.5),      # small indecision
        (96.5, 108, 96, 107),    # large green
        (107, 108, 106, 107.5),  # unrelated
    ]
    df = _df(rows)
    morning, evening = concepts.morning_evening_star(df, small_body_max_pct=30.0)
    assert list(morning) == [False, False, True, False]
    assert not evening.any()


def test_evening_star_mirrors_morning_star():
    rows = [
        (96, 108, 95, 107),      # large green
        (107, 108, 106, 107.5),  # small indecision
        (107.5, 108, 96, 97),    # large red
    ]
    df = _df(rows)
    morning, evening = concepts.morning_evening_star(df, small_body_max_pct=30.0)
    assert list(evening) == [False, False, True]


def test_candle_pattern_confirmation_fires_only_once_edge_triggered():
    # bar 0: doji-like pattern event, high=101
    df = _df([
        (100, 101, 99, 100.2),
        (100.2, 100.8, 99.5, 100.5),  # close 100.5, still below pattern high 101 -- no confirm
        (100.5, 102, 100, 101.5),     # close 101.5 > 101 -- confirms (edge)
        (101.5, 103, 101, 102.5),     # still beyond 101, but already confirmed -- must NOT re-fire
    ])
    pattern = pd.Series([True, False, False, False], index=df.index)
    confirm = concepts.candle_pattern_confirmation(pattern, df, "bullish")
    assert list(confirm) == [False, False, True, False]


def test_structure_stop_loss_buffer_is_noop_by_default_backward_compat():
    """Every strategy using stop_loss.type='structure' before this session
    (e.g. Supply/Demand Zone's fallback chain) never set spec.value --
    confirming the new optional buffer defaults to 0% and changes nothing
    for them."""
    cfg = StrategyConfig(name="structure sl buffer noop test", timeframes={"entry": "1h"},
                          stop_loss=SLTPSpec(type="structure"))
    strat = ConfiguredStrategy(cfg)
    df = pd.DataFrame({"entry_support": [95.0], "close": [100.0]})
    sl = strat._compute_stop_loss(df, 0, 100.0, "bullish")
    assert sl == 95.0  # unbuffered -- exactly the raw zone value, as before


def test_structure_stop_loss_buffer_applies_when_set():
    cfg = StrategyConfig(name="structure sl buffer test", timeframes={"entry": "1h"},
                          stop_loss=SLTPSpec(type="structure", value=1.0))
    strat = ConfiguredStrategy(cfg)
    df = pd.DataFrame({"entry_support": [95.0], "close": [100.0]})
    sl = strat._compute_stop_loss(df, 0, 100.0, "bullish")
    assert sl == 95.0 * 0.99


def test_candlestick_patterns_wired_end_to_end_doji_long():
    cfg = StrategyConfig(
        name="candlestick wiring test",
        timeframes={"entry": "1h"},
        concepts_used=["candlestick_patterns"],
        long_entry_conditions=[Condition(type="concept", name="doji_confirm", direction="bullish", lookback_bars=1)],
        stop_loss=SLTPSpec(type="structure", value=1.0),
        take_profit=SLTPSpec(type="fixed_pct", value=4.0),
        risk_pct=1.0,
    )
    strat = ConfiguredStrategy(cfg)
    df = _df([
        (100, 101, 99, 100.1),          # doji: body=0.1, range=2 -> 5%, comfortably under 10%
        (100.1, 100.8, 99.5, 100.5),    # not yet confirmed
        (100.5, 102, 100, 101.5),       # confirms (close > 101)
    ])
    ConfiguredStrategy._compute_concept_columns(df, {"candlestick_patterns"})
    merged = df.add_prefix("entry_")
    cond = cfg.long_entry_conditions[0]
    results = [strat._eval(cond, merged, i) for i in range(len(merged))]
    assert results == [False, False, True]
