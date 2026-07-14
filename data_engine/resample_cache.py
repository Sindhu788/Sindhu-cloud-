"""Disk cache for resampled (non-1m) candle dataframes.

Resampling 1m candles into a higher timeframe is pure, deterministic work
over the same source data -- recomputing it on every backtest run (and every
optimizer candidate, and every re-backtest) is wasted CPU. This module
caches the resampled result for an EXACT (exchange, symbol, interval,
start_ms, end_ms) request, keyed also on the min/max open_time currently
stored for that symbol's 1m data.

Why exact-range keys instead of caching one full series and slicing it per
request: a boundary bucket that only partially overlaps [start_ms, end_ms]
is resampled from just the in-range 1m rows (a genuinely partial bar), not
from the full bucket's underlying data. Slicing a full precomputed series
would silently include out-of-range rows in that boundary bucket and change
the result. Exact-range keys reproduce the original per-call computation
byte-for-byte while still caching the two patterns that actually repeat in
this pipeline: a pipeline re-backtest reusing the original run's exact
settings, and the optimizer scoring many candidates against the same fixed
fast-subset window.

Invalidation is automatic: if new 1m data has been downloaded since the
cache entry was written, get_symbol_time_bounds() no longer matches the
entry's stored bounds, so it's treated as a miss and recomputed -- no
explicit "clear cache on download" wiring needed.

Cache files live under data/market_data/resample_cache/ and are written
atomically (temp file + os.replace) so concurrent backtest worker processes
never observe a half-written entry.
"""

import os
import json
import hashlib
import tempfile

import pandas as pd

from data_engine.paths import MARKET_DATA_DIR

CACHE_DIR = os.path.join(MARKET_DATA_DIR, "resample_cache")


def _safe_symbol(symbol):
    return symbol.replace("/", "-")


def _range_tag(start_ms, end_ms):
    """Short, filesystem-safe tag for an exact (start_ms, end_ms) pair.
    Hashed rather than embedded raw since None/arbitrary large ints would
    otherwise make for unwieldy filenames."""
    raw = f"{start_ms}_{end_ms}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


def _paths(exchange, symbol, interval, start_ms, end_ms):
    base = f"{exchange}__{_safe_symbol(symbol)}__{interval}__{_range_tag(start_ms, end_ms)}"
    return (
        os.path.join(CACHE_DIR, base + ".pkl"),
        os.path.join(CACHE_DIR, base + ".meta.json"),
    )


def load(exchange, symbol, interval, start_ms, end_ms, source_bounds):
    """Return the cached dataframe for this exact request if it's fresh for
    `source_bounds` (the current (min_open_time, max_open_time) of the
    symbol's 1m data), else None."""
    data_path, meta_path = _paths(exchange, symbol, interval, start_ms, end_ms)
    if not (os.path.exists(data_path) and os.path.exists(meta_path)):
        return None
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, ValueError):
        return None
    if tuple(meta.get("source_bounds", [])) != tuple(source_bounds):
        return None
    if meta.get("start_ms") != start_ms or meta.get("end_ms") != end_ms:
        return None  # hash collision guard
    try:
        return pd.read_pickle(data_path)
    except (OSError, ValueError, EOFError):
        return None


def save(exchange, symbol, interval, start_ms, end_ms, df, source_bounds):
    """Atomically write `df` as the cache entry for this exact
    (exchange, symbol, interval, start_ms, end_ms) request, tagged with the
    source bounds it was computed from."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    data_path, meta_path = _paths(exchange, symbol, interval, start_ms, end_ms)

    fd, tmp_data = tempfile.mkstemp(dir=CACHE_DIR, prefix=".tmp_", suffix=".pkl")
    os.close(fd)
    df.to_pickle(tmp_data)
    os.replace(tmp_data, data_path)

    fd, tmp_meta = tempfile.mkstemp(dir=CACHE_DIR, prefix=".tmp_", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"source_bounds": list(source_bounds), "start_ms": start_ms, "end_ms": end_ms}, f)
    os.replace(tmp_meta, meta_path)


def clear_all():
    """Wipe every cached resample entry. Not needed for normal operation
    (invalidation is automatic via source_bounds) -- exposed for manual
    troubleshooting only."""
    if not os.path.isdir(CACHE_DIR):
        return 0
    removed = 0
    for name in os.listdir(CACHE_DIR):
        try:
            os.remove(os.path.join(CACHE_DIR, name))
            removed += 1
        except OSError:
            pass
    return removed
