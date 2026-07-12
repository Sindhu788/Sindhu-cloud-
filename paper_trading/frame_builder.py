"""Builds an entry_-prefixed indicator frame for evaluating lessons that
have no strategy attached to them (a standalone Lesson-triggered signal).
When a lesson rides alongside a strategy's own signal, it's evaluated
directly against that strategy's already-prepared dataframe instead (same
as backtesting) -- this module only exists for the "no strategy, lesson
alone" path, and computes the common concepts.py indicator set plus
anything nonstandard the given lessons' conditions ask for.
"""

from backtest_engine import concepts
from data_engine.resample import get_ohlcv

_DEFAULT_PERIOD = {"ema": 20, "sma": 20, "rsi": 14, "atr": 14}


def _add_indicator(df, name, period):
    col = f"{name}_{period}"
    if col in df.columns:
        return
    if name == "ema":
        df[col] = concepts.ema(df["close"], period)
    elif name == "sma":
        df[col] = concepts.sma(df["close"], period)
    elif name == "rsi":
        df[col] = concepts.rsi(df["close"], period)
    elif name == "atr":
        df[col] = concepts.atr(df, period)


def build_entry_frame(exchange, symbol, timeframe, lessons, start_ms=None, end_ms=None):
    df = get_ohlcv(exchange, symbol, timeframe, start_ms=start_ms, end_ms=end_ms)
    if df is None or len(df) < 30:
        return None
    df = df.copy()

    for name in ("ema", "sma", "rsi", "atr"):
        _add_indicator(df, name, _DEFAULT_PERIOD[name])

    for lesson in lessons:
        for cond in lesson.conditions:
            if cond.type == "indicator_compare" and cond.indicator in _DEFAULT_PERIOD:
                period = cond.params.get("period") or _DEFAULT_PERIOD[cond.indicator]
                _add_indicator(df, cond.indicator, period)

    df["bull_bos"], df["bear_bos"] = concepts.break_of_structure(df)
    df["bull_choch"], df["bear_choch"] = concepts.change_of_character(df)
    df["bull_fvg"], df["bear_fvg"] = concepts.fair_value_gap(df)
    bl, bh, brl, brh = concepts.order_blocks(df)
    df["bull_ob_low"], df["bull_ob_high"] = bl, bh
    df["bear_ob_low"], df["bear_ob_high"] = brl, brh
    bbl, bbh, brbl, brbh = concepts.breaker_blocks(df)
    df["bull_breaker_low"], df["bull_breaker_high"] = bbl, bbh
    df["bear_breaker_low"], df["bear_breaker_high"] = brbl, brbh
    df["support"], df["resistance"] = concepts.support_resistance(df)
    df["volume_spike"] = concepts.volume_filter(df)
    df["session"] = concepts.session_column(df)
    df["trend_dir"] = concepts.trend_filter(df)
    df["pdh"], df["pdl"] = concepts.previous_day_high_low(df)
    df["pdl_sweep"], df["pdh_sweep"] = concepts.pdh_pdl_sweep(df)
    df["bull_liquidity_sweep"], df["bear_liquidity_sweep"] = concepts.liquidity_sweep(df)

    entry_df = df.add_prefix("entry_")
    entry_df["close"] = df["close"]
    return entry_df
