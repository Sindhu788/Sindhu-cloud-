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

Cache files live under data/market_data/resample_cache/<exchange>__<symbol>/
and are written atomically (temp file + os.replace) so concurrent backtest
worker processes never observe a half-written entry.

Sharded one subdirectory per (exchange, symbol): a single flat directory
holding every entry for every symbol grew to 212,000+ files within 12 days
of normal use (Paper Trading's coin filter + the Market page each score all
~50 tracked symbols repeatedly), and NTFS individual file lookup/create
performance degrades badly once a single directory holds that many entries
-- a single cache existence check was measured taking 1.2-1.8s, regardless
of hit or miss, which was the dominant cost, bigger than any recomputation.
Sharding by symbol keeps each directory's entry count low (proportional to
how many distinct exact-range requests that ONE symbol has ever received,
not all 50 combined) so lookups stay fast as the cache keeps growing.
"""

import os
import json
import hashlib
import shutil
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


def _shard_dir(exchange, symbol):
    return os.path.join(CACHE_DIR, f"{exchange}__{_safe_symbol(symbol)}")


def _paths(exchange, symbol, interval, start_ms, end_ms):
    base = f"{interval}__{_range_tag(start_ms, end_ms)}"
    shard = _shard_dir(exchange, symbol)
    return (
        os.path.join(shard, base + ".pkl"),
        os.path.join(shard, base + ".meta.json"),
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
    shard = _shard_dir(exchange, symbol)
    os.makedirs(shard, exist_ok=True)
    data_path, meta_path = _paths(exchange, symbol, interval, start_ms, end_ms)

    fd, tmp_data = tempfile.mkstemp(dir=shard, prefix=".tmp_", suffix=".pkl")
    os.close(fd)
    df.to_pickle(tmp_data)
    os.replace(tmp_data, data_path)

    fd, tmp_meta = tempfile.mkstemp(dir=shard, prefix=".tmp_", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"source_bounds": list(source_bounds), "start_ms": start_ms, "end_ms": end_ms}, f)
    os.replace(tmp_meta, meta_path)


def clear_all():
    """Wipe every cached resample entry (every per-symbol shard directory,
    plus any legacy flat-layout files left over from before sharding).
    Not needed for normal operation (invalidation is automatic via
    source_bounds) -- exposed for manual troubleshooting only."""
    if not os.path.isdir(CACHE_DIR):
        return 0
    removed = 0
    for name in os.listdir(CACHE_DIR):
        full = os.path.join(CACHE_DIR, name)
        try:
            if os.path.isdir(full):
                n = sum(len(files) for _, _, files in os.walk(full))
                shutil.rmtree(full)
                removed += n
            else:
                os.remove(full)
                removed += 1
        except OSError:
            pass
    return removed
