"""Evidence tests for the structure-level fixes kept from the Codex branch:
support/resistance levels must be the actual pivot price (not the price of the
later confirmation bar), must be causal, and RSI of a gain-only window is 100."""
import numpy as np
import pandas as pd

from backtest_engine import concepts


def _frame(n=300, seed=7):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    high = close + rng.uniform(0.1, 1.0, n)
    low = close - rng.uniform(0.1, 1.0, n)
    idx = pd.date_range("2026-01-01", periods=n, freq="1h")
    return pd.DataFrame({"open": close, "high": high, "low": low, "close": close, "volume": 1.0}, index=idx)


def test_resistance_levels_are_real_pivot_highs():
    df = _frame()
    k = 2
    _, resistance = concepts.support_resistance(df, k)
    pivots = df["high"] == df["high"].rolling(2 * k + 1, center=True).max()
    pivot_values = set(np.round(df["high"][pivots].values, 10))
    levels = resistance.dropna().values
    assert len(levels) > 0
    assert all(round(v, 10) in pivot_values for v in levels)


def test_levels_are_causal_future_bars_never_change_past_values():
    df = _frame()
    _, full = concepts.support_resistance(df, 2)
    for t in (80, 150, 220):
        part = concepts.support_resistance(df.iloc[: t + 1], 2)[1].iloc[-1]
        both_nan = pd.isna(part) and pd.isna(full.iloc[t])
        assert both_nan or part == full.iloc[t]


def test_rsi_gain_only_window_is_100_not_50():
    rising = pd.Series(np.arange(1, 80, dtype=float))
    assert concepts.rsi(rising).iloc[-1] == 100.0
    flat = pd.Series([5.0] * 80)
    assert concepts.rsi(flat).iloc[-1] == 50.0
