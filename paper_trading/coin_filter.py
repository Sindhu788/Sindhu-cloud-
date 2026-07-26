"""Coin Filter -- the Smart Analysis Pipeline's first real gate. Never
analyze every coin every tick: rank all tracked coins by recent volume,
trend strength, and volatility, and only hand the top N (paper_trading
config: coin_filter_top_n) on to the rest of the pipeline. Reuses the same
1m -> 1h resample path the Market page already uses, so this is read-only
against the existing klines_1m table -- no new data source.
"""

import time

from data_engine import storage
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


def _coin_activity_score(exchange, symbol):
    now_ms = int(time.time() * 1000)
    end_ms = now_ms - (now_ms % _CACHE_BUCKET_MS)
    start_ms = end_ms - _LOOKBACK_HOURS * 3600 * 1000
    df = get_ohlcv(exchange, symbol, interval="1h", start_ms=start_ms, end_ms=end_ms)
    if len(df) < 10:
        return None

    closes = df["close"]
    volume = df["volume"]
    returns = closes.pct_change().dropna()

    volume_score = float(volume.tail(24).mean())
    volatility_score = float(returns.std() * 100) if len(returns) else 0.0
    ema_fast = closes.ewm(span=8, adjust=False).mean()
    ema_slow = closes.ewm(span=21, adjust=False).mean()
    trend_score = abs(float((ema_fast.iloc[-1] - ema_slow.iloc[-1]) / ema_slow.iloc[-1] * 100)) if ema_slow.iloc[-1] else 0.0

    return {
        "symbol": symbol,
        "volume": volume_score,
        "volatility_pct": round(volatility_score, 4),
        "trend_strength_pct": round(trend_score, 4),
        "last_close_time": int(df.index[-1].timestamp() * 1000),
    }


def shortlist(exchange, symbols, top_n):
    """Returns the top_n symbols ranked by a simple, transparent activity
    score (volume rank + volatility rank + trend rank), each with its raw
    metrics attached so the rest of the pipeline (and the dashboard) can
    show why a coin was picked."""
    scored = []
    for symbol in symbols:
        try:
            s = _coin_activity_score(exchange, symbol)
        except Exception:
            s = None
        if s:
            scored.append(s)

    if not scored:
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
