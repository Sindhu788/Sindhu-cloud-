import time

from fastapi import APIRouter

from data_engine import storage, config
from data_engine.exchanges.registry import get_exchange_client
from data_engine.resample import get_ohlcv
from sindhu_web import cache
from sindhu_web.api.data import _default_exchange

router = APIRouter()


# get_ohlcv's on-disk resample cache is keyed on the EXACT (start_ms, end_ms)
# of the request. A raw time.time()-relative end_ms made every call unique --
# a guaranteed cache miss for all ~50 symbols on every request, forcing a
# full resample from raw 1m klines each time (measured ~1-2s/symbol, which
# is how a cold /api/market request could blow past a 15s client timeout).
# Flooring end_ms to this boundary lets repeated requests within the same
# window reuse the same cache entry -- this is a dashboard display signal,
# not a trade decision, so a few minutes of staleness is fine.
_CACHE_BUCKET_MS = 5 * 60 * 1000

# Even with the on-disk resample cache hitting, get_ohlcv() still calls
# storage.get_symbol_time_bounds() up front on every call to check
# freshness -- a plain indexed SQLite query that measured ~1-1.5s under the
# write load the Paper Trading engine's own tick generates concurrently
# (each storage call opens its own fresh connection; see
# storage.get_conn()). This in-memory, bucket-aligned cache skips that
# DB round-trip entirely for repeat requests within the same window --
# same staleness tolerance as the disk-cache bucket above.
_signal_cache = {}


def _signal_and_volatility(exchange_id, symbol):
    """Cheap, honest-effort signal (price vs 20-period EMA on 1h candles)
    and volatility (stdev of 1h returns, %) -- reads only the last ~50
    hours of candles per coin via the indexed (exchange, symbol, open_time)
    range query, so it stays fast even against a multi-million-row table."""
    now_ms = int(time.time() * 1000)
    end_ms = now_ms - (now_ms % _CACHE_BUCKET_MS)
    start_ms = end_ms - 50 * 3600 * 1000

    cache_key = (exchange_id, symbol, end_ms)
    if cache_key in _signal_cache:
        return _signal_cache[cache_key]

    df = get_ohlcv(exchange_id, symbol, interval="1h", start_ms=start_ms, end_ms=end_ms)
    if len(df) < 5:
        result = ("Neutral", None)
        _signal_cache[cache_key] = result
        return result

    closes = df["close"]
    ema20 = closes.ewm(span=20, adjust=False).mean()
    last_close, last_ema = closes.iloc[-1], ema20.iloc[-1]
    if last_close > last_ema * 1.001:
        signal = "Bullish"
    elif last_close < last_ema * 0.999:
        signal = "Bearish"
    else:
        signal = "Neutral"

    returns = closes.pct_change().dropna()
    volatility_pct = round(float(returns.std() * 100), 3) if len(returns) else None
    result = (signal, volatility_pct)
    _signal_cache[cache_key] = result
    if len(_signal_cache) > 500:
        stale = [k for k in _signal_cache if k[2] != end_ms]
        for k in stale:
            del _signal_cache[k]
    return result


@router.get("/api/market")
def get_market():
    exchange_id = _default_exchange()
    coins_cfg = config.load_or_seed("coins.json", config.DEFAULTS["coins.json"])
    quote = coins_cfg["quote_asset"]
    symbols = storage.load_symbols(exchange_id)

    def _compute():
        client = get_exchange_client(exchange_id)
        tickers = client.get_tickers(quote)
        rows = []
        for s in symbols:
            t = tickers.get(s)
            if not t:
                continue
            change_pct = t["change_pct"] or 0.0
            signal, volatility_pct = _signal_and_volatility(exchange_id, s)
            rows.append({
                "symbol": s, "price": t["price"], "change_pct": change_pct,
                "volume": t["volume"], "trend": "up" if change_pct >= 0 else "down",
                "signal": signal, "volatility_pct": volatility_pct,
            })
        return rows

    # Non-blocking: get_tickers() is a live exchange API call that measured
    # 60-130s in this environment. It's already pre-warmed at boot (see
    # server._warm_caches), but a request landing before that warm-up
    # finishes -- e.g. right after a restart -- used to block on the same
    # 60-130s call itself. Same class of bug as the /api/home disk-walk
    # hang: no user request should ever be the one to pay for a first
    # compute this expensive.
    rows = cache.cached_nonblocking(f"market_{exchange_id}", 30, _compute, [])
    return {"exchange": exchange_id, "quote": quote, "coins": rows}
