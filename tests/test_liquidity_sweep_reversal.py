"""Liquidity Sweep Reversal Strategy's core distinction: a sweep WITHOUT a
reclaim (genuine breakout/continuation) must NOT generate a false signal --
only sweep-THEN-reclaim, sequence-ordered, counts."""

import pandas as pd

from backtest_engine import concepts
from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from backtest_engine.configured_strategy import ConfiguredStrategy


def _df(rows):
    idx = pd.date_range("2026-01-01", periods=len(rows), freq="15min", tz="UTC")
    return pd.DataFrame({
        "open": [r[0] for r in rows], "high": [r[1] for r in rows],
        "low": [r[2] for r in rows], "close": [r[3] for r in rows],
    }, index=idx)


def test_sweep_without_reclaim_never_confirms():
    # A clean, sustained breakdown below support with NO reclaim -- this is
    # the genuine breakout/continuation case that must be REJECTED, not
    # mistaken for a reversal signal.
    rows = [(100, 101, 99, 100) for _ in range(10)]  # builds a support level around 99
    # breaks down and STAYS down, no reclaim -- slightly varying (not
    # perfectly identical) bars, matching real market data and avoiding a
    # degenerate swing-detection edge case that perfectly repeated OHLC
    # values can trigger.
    rows += [(91 - i * 0.05, 91.5 - i * 0.05, 90 - i * 0.05, 90.5 - i * 0.05) for i in range(20)]
    df = _df(rows)
    bull_sweep, bear_sweep, bull_reclaim, bear_reclaim = concepts.level_sweep_reclaim(df)
    long_confirm = concepts.sequential_event(bull_sweep, bull_reclaim)
    assert bull_sweep.any(), "test setup should have produced a real sweep"
    assert not long_confirm.any(), "sweep-without-reclaim incorrectly generated a signal"


def test_sweep_then_reclaim_correctly_confirms():
    rows = [(100, 101, 99, 100) for _ in range(10)]
    rows.append((99, 99.5, 90, 91))       # sweeps below support
    rows.append((91, 92, 90.5, 91.5))     # still below
    rows.append((91.5, 101, 91, 100.5))   # reclaims -- closes back above support
    df = _df(rows)
    bull_sweep, bear_sweep, bull_reclaim, bear_reclaim = concepts.level_sweep_reclaim(df)
    long_confirm = concepts.sequential_event(bull_sweep, bull_reclaim)
    assert long_confirm.iloc[12] == True


def test_soft_trend_filter_allows_reversal_against_bearish_pressure():
    """valid_structure_trend_soft(bullish) means "not strongly bearish" --
    must ALLOW when trend is undetermined (None), and REJECT only when
    trend is actually "down"."""
    cfg = StrategyConfig(name="soft trend test", timeframes={"entry": "1h"},
                          concepts_used=["valid_structure_trend"])
    strat = ConfiguredStrategy(cfg)
    df = pd.DataFrame({
        "entry_structure_trend": ["down", "up", None],
        "entry_trend_not_down": [False, True, True],
        "entry_trend_not_up": [True, False, True],
    })
    cond = Condition(type="concept", name="valid_structure_trend_soft", direction="bullish")
    results = [strat._eval(cond, df, i) for i in range(3)]
    assert results == [False, True, True]  # rejected only when strongly bearish


def test_liquidity_sweep_reclaim_concept_wired_end_to_end():
    cfg = StrategyConfig(
        name="liquidity sweep wiring test",
        timeframes={"entry": "15m"},
        concepts_used=["liquidity_sweep_reclaim"],
        long_entry_conditions=[Condition(type="concept", name="liquidity_sweep_reclaim",
                                          direction="bullish", lookback_bars=1)],
        stop_loss=SLTPSpec(type="signal_candle", value=1.0),
        take_profit=SLTPSpec(type="rr", value=2.0),
        risk_pct=1.0,
    )
    strat = ConfiguredStrategy(cfg)
    rows = [(100, 101, 99, 100) for _ in range(10)]
    rows.append((99, 99.5, 90, 91))
    rows.append((91, 92, 90.5, 91.5))
    rows.append((91.5, 101, 91, 100.5))
    df = _df(rows)
    ConfiguredStrategy._compute_concept_columns(df, {"liquidity_sweep_reclaim"})
    merged = df.add_prefix("entry_")
    cond = cfg.long_entry_conditions[0]
    results = [strat._eval(cond, merged, i) for i in range(len(merged))]
    assert results[12] is True
    assert not any(results[:12])
