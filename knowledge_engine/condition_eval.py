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

# Every "concept" condition name this evaluator actually dispatches to a
# real check below -- anything else (e.g. a bare "sma"/"ema"/"rsi" concept
# with no comparison, which isn't a pattern this evaluator recognizes at
# all) silently falls through to the final `return False` at the bottom of
# the "concept" branch, meaning it evaluates False on EVERY bar, forever.
# Used by knowledge_engine.lesson.Lesson.is_enforceable() to tell a real,
# evaluable condition apart from a guaranteed-always-false placeholder --
# diagnosed live: one lesson ("**Philosophy:** The backtest must account
# for a high frequency...") was saved with a single bare `concept: sma`
# condition and rule_type="require_if_true", so it silently vetoed EVERY
# single trade attempt across the entire system's history (37,968,340
# rejections, 0 approvals) without ever being flagged as broken.
_DISPATCHABLE_CONCEPT_NAMES = {
    "bos", "choch", "fvg", "liquidity_sweep", "pdh_sweep", "pdl_sweep",
    "order_block", "breaker_block", "volume", "pdh", "pdl",
}


def condition_is_executable(cond):
    """True if `cond` maps to a real, non-trivially-always-false branch in
    evaluate_condition() below. A "raw" condition (never executable) or a
    "concept" condition whose name isn't one of the patterns this evaluator
    actually recognizes both return False -- see _DISPATCHABLE_CONCEPT_NAMES
    above for why a bare, unrecognized concept name is the dangerous case."""
    cond_type = getattr(cond, "type", None) if not isinstance(cond, dict) else cond.get("type")
    if cond_type == "raw":
        return False
    if cond_type == "concept":
        name = getattr(cond, "name", None) if not isinstance(cond, dict) else cond.get("name")
        return name in _DISPATCHABLE_CONCEPT_NAMES
    return cond_type in ("indicator_compare", "price_compare", "session", "trend")


def _array(df, col, arr_cache):
    if arr_cache is None:
        return None
    arr = arr_cache.get(col)
    if arr is None:
        if col not in df.columns:
            return None
        arr = df[col].to_numpy()
        arr_cache[col] = arr
    return arr


def _get(df, i, col, arr_cache=None):
    # arr_cache (optional): a per-symbol-backtest dict the caller keeps
    # across many calls (see KnowledgeEngine.check()) so each column is
    # converted from a pandas Series to a numpy array once instead of
    # re-slicing a Series on every single bar -- same fix and same
    # reasoning as backtest_engine/configured_strategy.py's _array(), which
    # profiling showed was the dominant per-bar cost. Falls back to the
    # original pandas-based lookup when no cache is passed (paper trading's
    # signal_generator.py calls this far less often, so it isn't worth the
    # extra bookkeeping there).
    arr = _array(df, col, arr_cache)
    if arr is not None:
        val = arr[i]
        return None if pd.isna(val) else val
    if arr_cache is not None:
        return None  # column truly doesn't exist
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


def evaluate_condition(df, i, cond, arr_cache=None):
    # arr_cache (optional): pass a dict the caller keeps across many calls
    # against the same `df` (see KnowledgeEngine.check()) to avoid
    # re-slicing pandas Series on every bar. Omit it (as paper trading's
    # signal_generator.py does) for the exact original per-call behavior.
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
            arr = _array(df, col, arr_cache)
            if arr is not None:
                start = max(0, i - window + 1)
                return bool(arr[start:i + 1].any())
            if arr_cache is not None:
                return False  # column truly doesn't exist
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
            return _get(df, i, "entry_bull_ob_low", arr_cache) is not None or _get(df, i, "entry_bear_ob_low", arr_cache) is not None
        if cond.name == "breaker_block":
            return _get(df, i, "entry_bull_breaker_low", arr_cache) is not None or _get(df, i, "entry_bear_breaker_low", arr_cache) is not None
        if cond.name == "volume":
            return _within("entry_volume_spike")
        if cond.name in ("pdh", "pdl"):
            return _get(df, i, f"entry_{cond.name}", arr_cache) is not None
        return False

    if cond.type == "indicator_compare":
        val = _get(df, i, _indicator_column(cond.indicator, cond.params), arr_cache)
        if val is None:
            return False
        ops = {"<": val < cond.value, ">": val > cond.value,
               "<=": val <= cond.value, ">=": val >= cond.value}
        return ops.get(cond.op, False)

    if cond.type == "price_compare":
        price = _get(df, i, "close", arr_cache)
        if price is None:
            price = _get(df, i, "entry_close", arr_cache)
        ind_val = _get(df, i, _indicator_column(cond.indicator, cond.params), arr_cache)
        if price is None or ind_val is None:
            return False
        return price > ind_val if cond.op == ">" else price < ind_val

    if cond.type == "session":
        return _get(df, i, "entry_session", arr_cache) == cond.name

    if cond.type == "trend":
        return _get(df, i, "entry_trend_dir", arr_cache) == cond.direction

    return False
