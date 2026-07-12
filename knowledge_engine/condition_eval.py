"""Standalone condition evaluator for lessons. Deliberately separate from
ConfiguredStrategy's own evaluator (backtest_engine/configured_strategy.py)
rather than sharing it -- lessons only ever look at the entry timeframe, so
this stays simpler, and it means the Knowledge Engine can never regress
Phase 2.1's strategy evaluation logic.

Missing columns (a lesson references a concept the strategy never
computed) resolve to "doesn't match" rather than raising -- a lesson that
can't be checked just doesn't gate anything for that bar.
"""

import pandas as pd

from backtest_engine import concepts

_DEFAULT_PERIOD = {"ema": 20, "sma": 20, "rsi": 14, "atr": 14}


def _get(df, i, col):
    if col not in df.columns:
        return None
    val = df[col].iloc[i]
    return None if pd.isna(val) else val


def _indicator_column(indicator_name, params):
    if indicator_name in ("pdh", "pdl"):
        return f"entry_{indicator_name}"
    period = params.get("period") or _DEFAULT_PERIOD.get(indicator_name, 14)
    if indicator_name in ("ema", "sma", "rsi", "atr"):
        return f"entry_{indicator_name}_{period}"
    return f"entry_{indicator_name}"


def evaluate_condition(df, i, cond):
    if cond.type == "raw":
        return False

    if cond.type == "concept":
        # Same lookback-window semantics as ConfiguredStrategy._eval
        # (backtest_engine/configured_strategy.py) -- kept as a separate
        # copy deliberately (see module docstring), but the Phase 6 windowed
        # -truth behavior must match so a lesson gates trades consistently
        # with how the strategy itself would evaluate the same condition.
        window = cond.lookback_bars if cond.lookback_bars is not None else 10

        def _within(col):
            if col not in df.columns:
                return False
            return concepts.true_within_lookback(df[col], i, window)

        event_colmap = {
            "bos": ("entry_bull_bos", "entry_bear_bos"),
            "choch": ("entry_bull_choch", "entry_bear_choch"),
            "fvg": ("entry_bull_fvg", "entry_bear_fvg"),
            "liquidity_sweep": ("entry_bull_liquidity_sweep", "entry_bear_liquidity_sweep"),
        }
        if cond.name in event_colmap:
            bull_col, bear_col = event_colmap[cond.name]
            if cond.direction == "bearish":
                return _within(bear_col)
            if cond.direction == "bullish":
                return _within(bull_col)
            return _within(bull_col) or _within(bear_col)
        if cond.name in ("pdh_sweep", "pdl_sweep"):
            return _within(f"entry_{cond.name}")
        if cond.name == "order_block":
            return _get(df, i, "entry_bull_ob_low") is not None or _get(df, i, "entry_bear_ob_low") is not None
        if cond.name == "breaker_block":
            return _get(df, i, "entry_bull_breaker_low") is not None or _get(df, i, "entry_bear_breaker_low") is not None
        if cond.name == "volume":
            return _within("entry_volume_spike")
        if cond.name in ("pdh", "pdl"):
            return _get(df, i, f"entry_{cond.name}") is not None
        return False

    if cond.type == "indicator_compare":
        val = _get(df, i, _indicator_column(cond.indicator, cond.params))
        if val is None:
            return False
        ops = {"<": val < cond.value, ">": val > cond.value,
               "<=": val <= cond.value, ">=": val >= cond.value}
        return ops.get(cond.op, False)

    if cond.type == "price_compare":
        price = _get(df, i, "close")
        if price is None:
            price = _get(df, i, "entry_close")
        ind_val = _get(df, i, _indicator_column(cond.indicator, cond.params))
        if price is None or ind_val is None:
            return False
        return price > ind_val if cond.op == ">" else price < ind_val

    if cond.type == "session":
        return _get(df, i, "entry_session") == cond.name

    if cond.type == "trend":
        return _get(df, i, "entry_trend_dir") == cond.direction

    return False
