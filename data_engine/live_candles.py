"""Live-only OHLCV source for the lightweight cloud runner.

The rest of the codebase's live pipeline (market_state.py, mtf_context.py,
coin_filter.py) all reads candles through data_engine.resample.get_ohlcv(),
which is backed by the klines_1m table -- fine on the local laptop where
that table is kept warm by the historical downloader, but the whole point
of the lightweight runner is that it must work WITHOUT that table (or the
45GB database it lives in) existing at all.

This module fetches candles directly from the exchange (Binance/ccxt) via
the same ExchangeClient.get_ohlcv() the local downloader already uses, and
returns them in the EXACT dataframe shape (columns, UTC DatetimeIndex)
data_engine.resample.get_ohlcv() already returns -- so market_state.py,
mtf_context.py and coin_filter.py need zero changes to consume it; only
resample.get_ohlcv()'s own top-level dispatch needs one new opt-in branch
(see resample.py) to hand requests to this module instead.

Candles are cached IN-MEMORY per (exchange, symbol, interval), refreshed
incrementally (only the new candles since the last fetch, same
resume-from-last-candle idea data_engine.downloader already uses for the
local database) rather than re-fetched from scratch on every call --
without this, a strategy needing 20 days of 1m history would re-request
~29,000 candles from Binance every single tick, which would both be
wasteful and risk exchange rate-limiting. The cache is process-local and
non-persistent by design: a cold restart just re-warms itself with one
paginated fetch per (symbol, interval) actually requested, same as the
local downloader's own "resume from last candle" pattern, just kept in
RAM instead of on disk since the cloud runner has no historical-data
mandate to persist candles at all.
"""

import threading
import time

import pandas as pd

from data_engine.config import REQUEST_DELAY_SECONDS
from data_engine.exchanges.registry import get_exchange_client
from data_engine.resample import _OUT_COLUMNS, _rows_to_df

# Binance (and ccxt exchanges, by the same convention) cap klines requests
# at 1000 rows per call -- matches KLINES_LIMIT's usual default but pinned
# explicitly here since this module's correctness (the pagination loop
# below) depends on it, not just performance.
_PAGE_LIMIT = 1000

# However much history a caller ever asks for, the in-memory cache only
# ever retains this many most-recent days per (exchange, symbol, interval)
# -- old rows are trimmed after every refresh so a long-running process
# doesn't grow this cache without bound. 25 days comfortably covers
# lookback_days=20 (paper_trading.signal_generator's default) with margin.
_MAX_RETENTION_DAYS = 25

_INTERVAL_MS = {
    "1m": 60_000, "3m": 3 * 60_000, "5m": 5 * 60_000, "15m": 15 * 60_000, "30m": 30 * 60_000,
    "1h": 3_600_000, "2h": 2 * 3_600_000, "4h": 4 * 3_600_000, "6h": 6 * 3_600_000,
    "12h": 12 * 3_600_000, "1d": 86_400_000, "1w": 7 * 86_400_000,
}

_lock = threading.Lock()
_cache = {}  # (exchange, symbol, interval) -> DataFrame, _OUT_COLUMNS, sorted by time ascending


def _now_ms():
    return int(time.time() * 1000)


def _normalize_row(r):
    """A real exchange kline response can carry extra trailing fields
    (Binance's raw response has 12; the shared 9-field convention this
    codebase standardizes on -- open_time, open, high, low, close, volume,
    close_time, quote_volume, trades -- only ever needs the first 9,
    exactly the same slicing data_engine.storage.insert_klines already
    does for the local downloader's own writes). Cast the same way too, so
    a live-fetched row is indistinguishable from a stored one once it
    reaches _rows_to_df."""
    return (r[0], float(r[1]), float(r[2]), float(r[3]), float(r[4]),
            float(r[5]), r[6], float(r[7]), int(r[8]))


def _fetch_page(client, symbol, interval, since_ms, limit=_PAGE_LIMIT):
    rows = client.get_ohlcv(symbol, interval, since_ms=since_ms, limit=limit)
    return [_normalize_row(r) for r in rows]


def _fetch_range(client, symbol, interval, start_ms, end_ms):
    """Paginated fetch covering [start_ms, end_ms], oldest-first. A short,
    courteous delay between pages (the same REQUEST_DELAY_SECONDS the local
    downloader already uses) keeps this from hammering the exchange's rate
    limit during a cold-start warmup that needs several pages."""
    interval_ms = _INTERVAL_MS[interval]
    all_rows = []
    cursor = start_ms
    while cursor < end_ms:
        rows = _fetch_page(client, symbol, interval, cursor)
        if not rows:
            break
        all_rows.extend(rows)
        last_open_time = rows[-1][0]
        cursor = last_open_time + interval_ms
        if len(rows) < _PAGE_LIMIT:
            break
        time.sleep(REQUEST_DELAY_SECONDS)
    return all_rows


def _trim(df, end_ms):
    if df.empty:
        # An empty frame from pd.DataFrame(columns=...) has a plain
        # RangeIndex, not a DatetimeIndex -- comparing it to a Timestamp
        # raises, and there is nothing to trim anyway.
        return df
    cutoff = pd.to_datetime(end_ms - _MAX_RETENTION_DAYS * 86_400_000, unit="ms", utc=True)
    return df[df.index >= cutoff]


def get_ohlcv_live(exchange, symbol, interval, start_ms=None, end_ms=None):
    """Drop-in replacement for data_engine.resample.get_ohlcv() that never
    touches the database -- every candle comes from a real, direct exchange
    API call (first request for a (symbol, interval) pair) or this
    process's own in-memory cache of one (subsequent requests)."""
    if interval not in _INTERVAL_MS:
        raise ValueError(f"live candle fetch does not support interval {interval!r}")

    now = end_ms if end_ms is not None else _now_ms()
    start = start_ms if start_ms is not None else now - _MAX_RETENTION_DAYS * 86_400_000
    key = (exchange, symbol, interval)
    client = get_exchange_client(exchange)

    with _lock:
        cached = _cache.get(key)

        if cached is None or cached.empty or cached.index.min() > pd.to_datetime(start, unit="ms", utc=True):
            # No cache yet, or the cache doesn't reach far enough back to
            # cover what's being asked for -- one full paginated fetch.
            rows = _fetch_range(client, symbol, interval, start, now)
            df = _rows_to_df(rows)[_OUT_COLUMNS] if rows else pd.DataFrame(columns=_OUT_COLUMNS)
        else:
            # Cache already covers the requested start -- only fetch
            # candles newer than what's already held, exactly the
            # "resume from last candle" idea the local downloader uses,
            # just kept in memory instead of in klines_1m.
            last_open_ms = int(cached.index.max().timestamp() * 1000)
            since = last_open_ms + _INTERVAL_MS[interval]
            new_rows = _fetch_range(client, symbol, interval, since, now) if since < now else []
            if new_rows:
                new_df = _rows_to_df(new_rows)[_OUT_COLUMNS]
                df = pd.concat([cached, new_df])
                df = df[~df.index.duplicated(keep="last")].sort_index()
            else:
                df = cached

        df = _trim(df, now)
        _cache[key] = df

    if df.empty:
        return df
    end_ts = pd.to_datetime(now, unit="ms", utc=True)
    start_ts = pd.to_datetime(start, unit="ms", utc=True)
    return df[(df.index >= start_ts) & (df.index <= end_ts)]


def clear_cache():
    """Test/debug hook -- drops every cached series so the next call is a
    guaranteed cold fetch."""
    with _lock:
        _cache.clear()
