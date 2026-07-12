import pandas as pd

from data_engine import storage
from data_engine.config import SUPPORTED_INTERVALS, RESAMPLE_RULE

_COLUMNS = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "trades"]


def _rows_to_df(rows):
    df = pd.DataFrame(rows, columns=_COLUMNS)
    df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df = df.set_index("timestamp")
    return df


def get_ohlcv(exchange, symbol, interval="1m", start_ms=None, end_ms=None):
    """Return an OHLCV dataframe for `symbol` on `exchange` at any supported
    timeframe. 1m data is the source of truth in the DB; everything else is
    derived from it on the fly via resampling."""
    if interval not in SUPPORTED_INTERVALS:
        raise ValueError(f"Unsupported interval {interval!r}. Choose from {SUPPORTED_INTERVALS}")

    rows = storage.get_klines_range(exchange, symbol, start_ms, end_ms)
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "quote_volume", "trades"])

    df = _rows_to_df(rows)

    if interval == "1m":
        return df[["open", "high", "low", "close", "volume", "quote_volume", "trades"]]

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
