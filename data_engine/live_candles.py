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
_MAX_PAGES = 400  # safety bound: 28,800 one-minute rows at 100 rows/page is 288 pages

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

_lock = threading.Lock()          # guards the dicts below only; it is NOT held while talking to the exchange
_key_locks = {}                   # (exchange, symbol, interval) -> Lock: one fetch per series at a time, different series in parallel
_keep_from = {}                   # key -> earliest start_ms ever requested (the cache keeps rows back to it, up to _MAX_KEEP_DAYS)
_covered_from = {}                # key -> start_ms from which the cache holds everything the exchange has (see get_ohlcv_live)
_MAX_KEEP_DAYS = 400              # hard bound: the longest lookback any caller uses is 365 days (1d candles, htf_confluence_filter)
_cache = {}  # (exchange, symbol, interval) -> DataFrame, _OUT_COLUMNS, sorted by time ascending

# Master plan A2 (P3): download counters, read by the engine once per scan (one summary line instead of a line per slow series).
# kinds: "cold" = no cache yet (one full window), "backfill" = only the OLDER part a new caller needs, "incremental" = only newer candles.
FETCH_STATS = {"requests": 0, "rows": 0, "cold": 0, "backfill": 0, "incremental": 0, "seconds": 0.0, "slow_series": 0}


def _verbose():
    """Master plan A18 (P29): the per-series 'slow download' / 'BACKFILL' lines (100+ per cold scan) are now counted in the per-scan
    [scan-stages] summary instead; SINDHU_VERBOSE_CANDLES=1 prints them again for a diagnosis."""
    import os
    return os.environ.get("SINDHU_VERBOSE_CANDLES") == "1"


def fetch_stats_snapshot():
    with _lock:
        return dict(FETCH_STATS)


def fetch_stats_delta(before):
    now = fetch_stats_snapshot()
    return {k: (round(now[k] - before.get(k, 0), 1) if k == "seconds" else now[k] - before.get(k, 0)) for k in now}


def _note_kind(kind):
    with _lock:
        FETCH_STATS[kind] += 1


def _note_fetch(pages, rows, seconds):
    with _lock:
        FETCH_STATS["requests"] += pages
        FETCH_STATS["rows"] += rows
        FETCH_STATS["seconds"] += seconds


# Master plan A5 (P5): a per-thread download deadline. The engine sets one per coin (and the prefetch phase one per run); the page loop
# checks it before every page. Past the deadline the download stops with FetchDeadlineExceeded: the coin is skipped for this scan by the
# engine's existing per-coin error path ("Market data unavailable; evaluation skipped"), the scan goes on with the next coin. Rows a
# FIRST (cold) download already received are kept, oldest first, so the next scan continues from there instead of starting over.
_tl = threading.local()


class FetchDeadlineExceeded(RuntimeError):
    def __init__(self, msg, rows=None):
        super().__init__(msg)
        self.rows = rows or []


def set_fetch_deadline(deadline_monotonic):
    """Deadline (time.monotonic() value) for downloads made by THIS thread; None clears it."""
    _tl.deadline = deadline_monotonic


def _check_deadline(symbol, interval, rows):
    d = getattr(_tl, "deadline", None)
    if d is not None and time.monotonic() > d:
        raise FetchDeadlineExceeded(f"download deadline reached for {symbol} {interval} after {len(rows)} rows", rows)


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
    pages = 0
    t_begin = time.monotonic()
    while cursor < end_ms and pages < _MAX_PAGES:
        try:
            _check_deadline(symbol, interval, all_rows)
        except FetchDeadlineExceeded:
            _note_fetch(pages, len(all_rows), time.monotonic() - t_begin)
            raise
        pages += 1
        rows = _fetch_page(client, symbol, interval, cursor)
        if not rows:
            break
        all_rows.extend(rows)
        last_open_time = rows[-1][0]
        next_cursor = last_open_time + interval_ms
        # Do NOT stop just because a page is shorter than _PAGE_LIMIT: OKX/Bitget/Gate cap a request at 100-300 rows,
        # so a short page is normal and stopping there left the cache ~a week behind (every frame then failed the
        # stale-candle guard on Cloud). Stop only when the data reaches the end or the cursor stops advancing.
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        time.sleep(REQUEST_DELAY_SECONDS)
    took = time.monotonic() - t_begin
    _note_fetch(pages, len(all_rows), took)
    if took > 20:   # diagnosis only: shows in the Render log which series make a scan slow
        with _lock:
            FETCH_STATS["slow_series"] += 1
    if took > 20 and _verbose():
        print(f"[live-candles] slow download {symbol} {interval}: {len(all_rows)} rows, {pages} pages, {took:.0f}s, "
              f"window {(end_ms - start_ms) / 86_400_000:.0f} days", flush=True)
    return all_rows


def _trim(df, end_ms, keep_from_ms=None):
    """Drop rows older than the retention window. The window is _MAX_RETENTION_DAYS, widened (never beyond _MAX_KEEP_DAYS) to the
    earliest start any caller has asked for on this series. Before this, a caller that wants more than 25 days (the higher-timeframe
    trend filter asks for 30 days of 15m, 90 of 1h, 180 of 4h, 365 of 1d) found the cache "not far enough back" on EVERY call and
    re-downloaded the whole range each time, which is what made a cold scan take 15+ minutes on the free plan."""
    if df.empty:
        # An empty frame from pd.DataFrame(columns=...) has a plain
        # RangeIndex, not a DatetimeIndex -- comparing it to a Timestamp
        # raises, and there is nothing to trim anyway.
        return df
    cutoff_ms = end_ms - _MAX_RETENTION_DAYS * 86_400_000
    if keep_from_ms is not None:
        cutoff_ms = min(cutoff_ms, max(keep_from_ms, end_ms - _MAX_KEEP_DAYS * 86_400_000))
    cutoff = pd.to_datetime(cutoff_ms, unit="ms", utc=True)
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
        klock = _key_locks.setdefault(key, threading.Lock())

    with klock:
        with _lock:
            cached = _cache.get(key)

        with _lock:
            covered = _covered_from.get(key)
            keep = min(_keep_from.get(key, start), start)
            _keep_from[key] = keep
        # "Far enough back" = the cache starts at or before `start`, OR an earlier full download from a start at least that old already
        # returned everything the exchange has (a coin listed 40 days ago can never fill a 90-day window; do not retry forever).
        reaches_back = (not (cached is None or cached.empty)) and (
            cached.index.min() <= pd.to_datetime(start, unit="ms", utc=True) or (covered is not None and start >= covered))
        if not reaches_back and not (cached is None or cached.empty) and _verbose():
            # a series we already hold is being extended backwards: say why (diagnosis; counted as "backfill" in [scan-stages])
            print(f"[live-candles] BACKFILL {symbol} {interval}: needs {(now - start) / 86_400_000:.1f}d, cache starts "
                  f"{(now - int(cached.index.min().timestamp() * 1000)) / 86_400_000:.1f}d ago, covered_from "
                  f"{'-' if covered is None else format((now - covered) / 86_400_000, '.1f') + 'd ago'}", flush=True)
        if cached is None or cached.empty:
            # No cache yet -- one full paginated fetch of the requested window.
            _note_kind("cold")
            try:
                rows = _fetch_range(client, symbol, interval, start, now)
            except FetchDeadlineExceeded as e:
                if e.rows:                                   # keep the part already downloaded; the next scan resumes after it
                    with _lock:
                        _cache[key] = _trim(_rows_to_df(e.rows)[_OUT_COLUMNS], now, keep)
                raise
            df = _rows_to_df(rows)[_OUT_COLUMNS] if rows else pd.DataFrame(columns=_OUT_COLUMNS)
            if rows:
                with _lock:
                    _covered_from[key] = min(_covered_from.get(key, start), start)
        else:
            base = cached
            if not reaches_back:
                # Master plan A2 (P3): the cache holds the recent part already (e.g. 3 days) and a caller needs more (e.g. 20 days).
                # Download ONLY the missing older segment [start, first cached candle) instead of the whole window again (Cloud log
                # 5 Nov: "REFETCH ... needs 20.0d, cache starts 3.0d ago" re-downloaded 20 days). If the exchange has nothing there,
                # the series is marked covered from `start` so it is never retried.
                first_open_ms = int(cached.index.min().timestamp() * 1000)
                _note_kind("backfill")
                older = _fetch_range(client, symbol, interval, start, first_open_ms)
                older = [r for r in older if r[0] < first_open_ms]
                if older:
                    base = pd.concat([_rows_to_df(older)[_OUT_COLUMNS], cached])
                    base = base[~base.index.duplicated(keep="last")].sort_index()
                with _lock:
                    _covered_from[key] = min(_covered_from.get(key, start), start)
            # Only fetch candles newer than what's already held ("resume from last candle"). Master plan A2: the newest cached row
            # was usually still FORMING when it was fetched; once its close time has passed, start the refresh AT that row so its
            # final open/high/low/close/volume replace the partial values (before, the partial row was kept for good and later
            # read as a closed candle). Same number of requests as before: the refresh happened at exactly this moment anyway.
            last_open_ms = int(base.index.max().timestamp() * 1000)
            next_open_ms = last_open_ms + _INTERVAL_MS[interval]
            since = last_open_ms if next_open_ms <= now else next_open_ms
            new_rows = []
            if next_open_ms < now:
                _note_kind("incremental")
                new_rows = _fetch_range(client, symbol, interval, since, now)
            cached = cached if base is cached else None   # a backfilled frame is new and must be stored below
            if new_rows:
                new_df = _rows_to_df(new_rows)[_OUT_COLUMNS]
                df = pd.concat([base, new_df])
                df = df[~df.index.duplicated(keep="last")].sort_index()
            else:
                df = base

        if df is not cached:                  # nothing new -> nothing to trim or store (was 5 ms x 1,100 calls per scan)
            df = _trim(df, now, keep)
            with _lock:
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
        _keep_from.clear()
        _covered_from.clear()


def freshness_counts(now_ms=None):
    """Master plan A20 (P28): for every cached (exchange, symbol, interval): is the newest CLOSED candle older than one period (the same
    rule paper_trading.market_data_guard uses to reject stale data)? Returns counts only (no per-coin list), plus the stale series
    names (capped at 20) for the dashboard badge."""
    now_ms = now_ms if now_ms is not None else _now_ms()
    with _lock:
        items = list(_cache.items())
    fresh = stale = 0
    stale_names, oldest = [], 0
    for (ex, sym, iv), df in items:
        if df is None or df.empty:
            continue
        period = _INTERVAL_MS[iv]
        last_open = int(df.index.max().timestamp() * 1000)
        last_close = last_open + period if last_open + period <= now_ms else last_open      # newest row may still be forming
        age = now_ms - last_close
        oldest = max(oldest, age)
        if age > period:
            stale += 1
            if len(stale_names) < 20:
                stale_names.append(f"{sym} {iv}")
        else:
            fresh += 1
    return {"series": fresh + stale, "fresh": fresh, "stale": stale, "oldest_age_s": oldest // 1000, "stale_examples": stale_names}
