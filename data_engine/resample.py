import pandas as pd

from data_engine import storage, resample_cache
from data_engine.config import SUPPORTED_INTERVALS, RESAMPLE_RULE

_COLUMNS = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "trades"]
_OUT_COLUMNS = ["open", "high", "low", "close", "volume", "quote_volume", "trades"]


def _rows_to_df(rows):
    df = pd.DataFrame(rows, columns=_COLUMNS)
    df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df = df.set_index("timestamp")
    return df


def _compute(exchange, symbol, interval, start_ms, end_ms):
    """Exact same algorithm as before caching existed: filter 1m rows to
    [start_ms, end_ms] first, then resample -- a boundary bucket that only
    partially overlaps the requested range is built from just the in-range
    1m rows, matching the original (uncached) behavior byte-for-byte."""
    rows = storage.get_klines_range(exchange, symbol, start_ms, end_ms)
    if not rows:
        return pd.DataFrame(columns=_OUT_COLUMNS)
    df = _rows_to_df(rows)
    rule = RESAMPLE_RULE[interval]
    resampled = df.resample(rule, label="left", closed="left").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
        "quote_volume": "sum",
        "trades": "sum",
    })
    return resampled.dropna(subset=["open"])


def get_ohlcv(exchange, symbol, interval="1m", start_ms=None, end_ms=None):
    """Return an OHLCV dataframe for `symbol` on `exchange` at any supported
    timeframe. 1m data is the source of truth in the DB; everything else is
    derived from it via resampling. Non-1m results are cached on disk per
    exact (exchange, symbol, interval, start_ms, end_ms) request and
    automatically invalidated when new 1m data is downloaded for that symbol
    (see data_engine.resample_cache for why exact-range keys, not a
    full-series-then-slice cache, are required for correctness)."""
    if interval not in SUPPORTED_INTERVALS:
        raise ValueError(f"Unsupported interval {interval!r}. Choose from {SUPPORTED_INTERVALS}")

    if interval == "1m":
        rows = storage.get_klines_range(exchange, symbol, start_ms, end_ms)
        if not rows:
            return pd.DataFrame(columns=_OUT_COLUMNS)
        return _rows_to_df(rows)[_OUT_COLUMNS]

    source_bounds = storage.get_symbol_time_bounds(exchange, symbol)
    if source_bounds == (None, None):
        return pd.DataFrame(columns=_OUT_COLUMNS)

    cached = resample_cache.load(exchange, symbol, interval, start_ms, end_ms, source_bounds)
    if cached is not None:
        return cached

    result = _compute(exchange, symbol, interval, start_ms, end_ms)
    resample_cache.save(exchange, symbol, interval, start_ms, end_ms, result, source_bounds)
    return result
