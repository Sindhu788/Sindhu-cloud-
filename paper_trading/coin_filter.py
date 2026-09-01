"""Coin Filter -- the Smart Analysis Pipeline's first real gate. Never
analyze every coin every tick: rank all tracked coins by recent volume,
trend strength, and volatility, and only hand the top N (paper_trading
config: coin_filter_top_n) on to the rest of the pipeline. Reuses the same
1m -> 1h resample path the Market page already uses, so this is read-only
against the existing klines_1m table -- no new data source.
"""

import time

from data_engine import storage
from data_engine.logging_setup import log as default_log
from data_engine.resample import get_ohlcv

_LOOKBACK_HOURS = 72

# get_ohlcv's on-disk resample cache is keyed on the EXACT (start_ms, end_ms)
# of the request (see data_engine.resample_cache for why). Using a raw
# time.time()-relative end_ms made every single call unique -- a guaranteed
# cache miss, every symbol, every tick, forcing a full resample from raw 1m
# klines each time (measured ~1-2s/symbol). Flooring end_ms to this boundary
# means repeated ticks within the same window reuse the exact same cache
# entry -- the score is a coin-ranking signal, not a trade decision, so a
# few minutes of staleness here is fine.
_CACHE_BUCKET_MS = 5 * 60 * 1000

# Even with the on-disk resample cache genuinely hitting, get_ohlcv() still
# calls storage.get_symbol_time_bounds() up front on every call to check
# freshness -- a plain indexed SQLite query that measured ~1-1.5s under the
# concurrent write load the live Paper Trading tick itself generates (each
# storage call opens its own fresh connection; see storage.get_conn()).
# That cost is paid once per symbol per tick regardless of the resample
# cache. This in-memory, bucket-aligned score cache skips the DB round-trip
# entirely for repeat calls within the same window -- same staleness
# tolerance as the disk-cache bucket above, just avoiding the query that
# turned out to still dominate. Safe to be process-local/non-persistent:
# worst case on a fresh process is one extra compute per symbol.
_score_cache = {}


def _coin_activity_score(exchange, symbol):
    now_ms = int(time.time() * 1000)
    end_ms = now_ms - (now_ms % _CACHE_BUCKET_MS)
    start_ms = end_ms - _LOOKBACK_HOURS * 3600 * 1000

    cache_key = (exchange, symbol, end_ms)
    if cache_key in _score_cache:
        return _score_cache[cache_key]

    df = get_ohlcv(exchange, symbol, interval="1h", start_ms=start_ms, end_ms=end_ms)
    if len(df) < 10:
        _score_cache[cache_key] = None
        return None

    closes = df["close"]
    volume = df["volume"]
    returns = closes.pct_change().dropna()

    volume_score = float(volume.tail(24).mean())
    volatility_score = float(returns.std() * 100) if len(returns) else 0.0
    ema_fast = closes.ewm(span=8, adjust=False).mean()
    ema_slow = closes.ewm(span=21, adjust=False).mean()
    trend_score = abs(float((ema_fast.iloc[-1] - ema_slow.iloc[-1]) / ema_slow.iloc[-1] * 100)) if ema_slow.iloc[-1] else 0.0

    score = {
        "symbol": symbol,
        "volume": volume_score,
        "volatility_pct": round(volatility_score, 4),
        "trend_strength_pct": round(trend_score, 4),
        "last_close_time": int(df.index[-1].timestamp() * 1000),
    }
    _score_cache[cache_key] = score
    if len(_score_cache) > 500:
        stale = [k for k in _score_cache if k[2] != end_ms]
        for k in stale:
            del _score_cache[k]
    return score


def shortlist(exchange, symbols, top_n, log=default_log):
    """Returns the top_n symbols ranked by a simple, transparent activity
    score (volume rank + volatility rank + trend rank), each with its raw
    metrics attached so the rest of the pipeline (and the dashboard) can
    show why a coin was picked.

    An empty return used to be completely silent: the per-symbol
    `except Exception: s = None` swallowed every error, and a total
    failure (e.g. every symbol's candle data too stale to score, which is
    exactly what a 21-day-stale database produced) looked identical to a
    healthy "no coin qualified today". The Paper Trading Engine then
    ticked forever doing nothing, with nothing anywhere saying why. Errors
    are now counted and logged, and a fully-empty shortlist explains
    itself -- diagnosis only, the ranking/selection behaviour below is
    byte-for-byte unchanged."""
    scored = []
    errors = 0
    first_error = None
    unscorable = 0
    for symbol in symbols:
        try:
            s = _coin_activity_score(exchange, symbol)
        except Exception as e:
            errors += 1
            if first_error is None:
                first_error = f"{symbol}: {e!r}"
            s = None
        if s:
            scored.append(s)
        elif errors == 0 or s is None:
            # _coin_activity_score returns None (no exception) when the
            # symbol has fewer than 10 usable candles in the lookback
            # window -- a data-freshness problem, not a crash.
            unscorable += 1

    if errors:
        log(f"[coin-filter] {errors} of {len(symbols)} symbols errored while scoring "
            f"(first: {first_error})")

    if not scored:
        log(f"[coin-filter] EMPTY SHORTLIST -- 0 of {len(symbols)} symbols could be scored "
            f"({errors} errored, {unscorable - errors} had under 10 candles in the last "
            f"{_LOOKBACK_HOURS}h). The Paper Trading Engine cannot open ANY position until "
            f"this is resolved -- the usual cause is stale market data, so run a data download.")
        return []

    def _rank(key, reverse=True):
        ordered = sorted(scored, key=lambda s: s[key], reverse=reverse)
        return {s["symbol"]: rank for rank, s in enumerate(ordered)}

    volume_rank = _rank("volume")
    volatility_rank = _rank("volatility_pct")
    trend_rank = _rank("trend_strength_pct")

    for s in scored:
        sym = s["symbol"]
        s["activity_score"] = -(volume_rank[sym] + volatility_rank[sym] + trend_rank[sym])

    scored.sort(key=lambda s: s["activity_score"], reverse=True)
    return scored[:top_n]
