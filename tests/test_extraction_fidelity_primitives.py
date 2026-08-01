"""Batch 2, Task 2 -- new strategy schema/engine primitives needed to
represent rules that were previously silently dropped during extraction
(diagnosed on PDH-PDL Signal Candle Strategy, Batch 1's Task 3):
  1. candle_range_pct condition -- "the signal candle's range must be
     between X% and Y%".
  2. sl_distance_filter_pct -- discard a trade if the computed stop-loss
     distance falls outside a percent range.
  3. min_risk_reward_filter + primary_target_lookback_bars -- discard a
     trade if a structural reference target (highest/lowest of the
     preceding N candles) doesn't clear a minimum risk:reward.
  4. stop_loss.type == "signal_candle" -- SL anchored to the signal bar's
     own high/low, buffered by a percent.

None of these change any existing SL/TP/entry_conditions behavior when
left unset (None/empty), and none touch core PnL/exit/trade-execution
math -- they only decide whether a signal becomes a Signal object at all
(discard filters) or how one existing SL type resolves to a price
(signal_candle).
"""

import pandas as pd
import pytest

from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from backtest_engine.configured_strategy import ConfiguredStrategy


def _make_df(rows):
    idx = pd.date_range("2026-01-01", periods=len(rows), freq="1min", tz="UTC")
    return pd.DataFrame({
        "open": [r[0] for r in rows], "high": [r[1] for r in rows],
        "low": [r[2] for r in rows], "close": [r[3] for r in rows],
        "volume": [100.0] * len(rows),
    }, index=idx)


# ------------------------------------------------------------ candle_range_pct

def _range_pct_config(min_pct=None, max_pct=None):
    return StrategyConfig(
        name="Range Filter Test", timeframes={"entry": "1m"},
        entry_conditions=[Condition(type="candle_range_pct", params={"min_pct": min_pct, "max_pct": max_pct})],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0), take_profit=SLTPSpec(type="fixed_pct", value=2.0),
        risk_pct=1.0,
    )


def test_candle_range_pct_rejects_a_candle_below_the_minimum():
    cfg = _range_pct_config(min_pct=1.0, max_pct=5.0)
    strat = ConfiguredStrategy(cfg)
    # range = (100.2-100)/100 = 0.2% -- below the 1.0% minimum
    df = _make_df([(100, 100.2, 100.0, 100.1)])
    signal = strat.on_bar(strat.prepare(df), 0, None)
    assert signal is None


def test_candle_range_pct_accepts_a_candle_within_bounds():
    cfg = _range_pct_config(min_pct=1.0, max_pct=5.0)
    strat = ConfiguredStrategy(cfg)
    # range = (102-100)/100 = 2% -- within [1%, 5%]
    df = _make_df([(100, 102, 100, 101)])
    signal = strat.on_bar(strat.prepare(df), 0, None)
    assert signal is not None


def test_candle_range_pct_rejects_a_candle_above_the_maximum():
    cfg = _range_pct_config(min_pct=0.1, max_pct=1.0)
    strat = ConfiguredStrategy(cfg)
    # range = (110-100)/100 = 10% -- above the 1.0% maximum
    df = _make_df([(100, 110, 100, 105)])
    signal = strat.on_bar(strat.prepare(df), 0, None)
    assert signal is None


# ------------------------------------------------------------ sl_distance_filter_pct

def _sl_distance_config(min_pct, max_pct):
    cfg = StrategyConfig(
        name="SL Distance Filter Test", timeframes={"entry": "1m"},
        entry_conditions=[Condition(type="indicator_compare", indicator="rsi", op="<", value=100.0)],
        stop_loss=SLTPSpec(type="fixed_pct", value=0.1), take_profit=SLTPSpec(type="fixed_pct", value=2.0),
        risk_pct=1.0,
    )
    cfg.sl_distance_filter_pct = {"min_pct": min_pct, "max_pct": max_pct}
    return cfg


def test_sl_distance_filter_discards_a_too_tight_stop():
    cfg = _sl_distance_config(min_pct=0.15, max_pct=1.5)  # SL is fixed_pct=0.1%, below the 0.15% floor
    strat = ConfiguredStrategy(cfg)
    df = _make_df([(100, 101, 99, 100)])
    df["entry_rsi_14"] = 50.0
    signal = strat.on_bar(strat.prepare(df), 0, None)
    assert signal is None


def test_sl_distance_filter_allows_a_stop_within_bounds():
    cfg = _sl_distance_config(min_pct=0.05, max_pct=1.5)  # 0.1% stop is within [0.05%, 1.5%]
    strat = ConfiguredStrategy(cfg)
    df = _make_df([(100, 101, 99, 100)])
    df["entry_rsi_14"] = 50.0
    signal = strat.on_bar(strat.prepare(df), 0, None)
    assert signal is not None


# ------------------------------------------------------------ min_risk_reward_filter

def _rr_filter_config(min_rr, lookback):
    cfg = StrategyConfig(
        name="RR Filter Test", timeframes={"entry": "1m"},
        entry_conditions=[Condition(type="indicator_compare", indicator="rsi", op="<", value=100.0)],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0), take_profit=SLTPSpec(type="fixed_pct", value=10.0),
        risk_pct=1.0,
    )
    cfg.min_risk_reward_filter = min_rr
    cfg.primary_target_lookback_bars = lookback
    return cfg


def test_rr_filter_discards_when_the_primary_target_is_too_close():
    cfg = _rr_filter_config(min_rr=2.0, lookback=3)
    strat = ConfiguredStrategy(cfg)
    # 3 flat bars (highest high == 101 throughout, close to entry price)
    # then a bullish entry bar -- SL 1% below entry, but the primary
    # target (101, the recent high) is far too close to clear RR >= 2.
    df = _make_df([(100, 101, 99, 100), (100, 101, 99, 100), (100, 101, 99, 100), (100, 101, 99, 100.5)])
    df["entry_rsi_14"] = 50.0
    signal = strat.on_bar(strat.prepare(df), 3, None)
    assert signal is None


def test_rr_filter_allows_when_the_primary_target_clears_the_bar():
    cfg = _rr_filter_config(min_rr=2.0, lookback=3)
    strat = ConfiguredStrategy(cfg)
    # Primary target (highest high of the preceding 3 bars) is 150 --
    # far enough from a ~100 entry with a 1% stop to clear RR >= 2.
    df = _make_df([(100, 150, 99, 100), (100, 101, 99, 100), (100, 101, 99, 100), (100, 101, 99, 100.5)])
    df["entry_rsi_14"] = 50.0
    signal = strat.on_bar(strat.prepare(df), 3, None)
    assert signal is not None


def test_rr_filter_is_a_noop_when_not_configured():
    cfg = StrategyConfig(
        name="No Filter", timeframes={"entry": "1m"},
        entry_conditions=[Condition(type="indicator_compare", indicator="rsi", op="<", value=100.0)],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0), take_profit=SLTPSpec(type="fixed_pct", value=2.0),
        risk_pct=1.0,
    )
    strat = ConfiguredStrategy(cfg)
    df = _make_df([(100, 101, 99, 100)])
    df["entry_rsi_14"] = 50.0
    signal = strat.on_bar(strat.prepare(df), 0, None)
    assert signal is not None


# ------------------------------------------------------------ stop_loss.type == "signal_candle"

def _signal_candle_sl_config(buffer_pct):
    return StrategyConfig(
        name="Signal Candle SL Test", timeframes={"entry": "1m"},
        entry_conditions=[Condition(type="indicator_compare", indicator="rsi", op="<", value=100.0)],
        stop_loss=SLTPSpec(type="signal_candle", value=buffer_pct),
        take_profit=SLTPSpec(type="fixed_pct", value=2.0),
        risk_pct=1.0,
    )


def test_signal_candle_stop_loss_short_uses_own_bars_high_plus_buffer():
    cfg = _signal_candle_sl_config(buffer_pct=0.3)
    cfg.entry_conditions = [Condition(type="indicator_compare", indicator="rsi", op="<", value=100.0, direction="bearish")]
    strat = ConfiguredStrategy(cfg)
    df = _make_df([(100, 102.5, 99, 98)])  # bearish candle, high=102.5
    df["entry_rsi_14"] = 50.0
    signal = strat.on_bar(strat.prepare(df), 0, None)
    assert signal is not None
    assert signal.action == "sell"
    assert signal.stop_loss == pytest.approx(102.5 * 1.003)


def test_signal_candle_stop_loss_long_uses_own_bars_low_minus_buffer():
    cfg = _signal_candle_sl_config(buffer_pct=0.3)
    cfg.entry_conditions = [Condition(type="indicator_compare", indicator="rsi", op="<", value=100.0, direction="bullish")]
    strat = ConfiguredStrategy(cfg)
    df = _make_df([(100, 103, 97.5, 102)])  # bullish candle, low=97.5
    df["entry_rsi_14"] = 50.0
    signal = strat.on_bar(strat.prepare(df), 0, None)
    assert signal is not None
    assert signal.action == "buy"
    assert signal.stop_loss == pytest.approx(97.5 * 0.997)
