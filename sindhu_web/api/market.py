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


def _signal_and_volatility(exchange_id, symbol):
    """Cheap, honest-effort signal (price vs 20-period EMA on 1h candles)
    and volatility (stdev of 1h returns, %) -- reads only the last ~50
    hours of candles per coin via the indexed (exchange, symbol, open_time)
    range query, so it stays fast even against a multi-million-row table."""
    now_ms = int(time.time() * 1000)
    end_ms = now_ms - (now_ms % _CACHE_BUCKET_MS)
    start_ms = end_ms - 50 * 3600 * 1000
    df = get_ohlcv(exchange_id, symbol, interval="1h", start_ms=start_ms, end_ms=end_ms)
    if len(df) < 5:
        return "Neutral", None

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
    return signal, volatility_pct


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

    rows = cache.cached(f"market_{exchange_id}", 30, _compute)
    return {"exchange": exchange_id, "quote": quote, "coins": rows}
