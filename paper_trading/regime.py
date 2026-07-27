"""Basic Market Regime Detection (Self-Learning Group, item 3): a
lightweight, well-documented heuristic that labels each tracked symbol's
current condition as one of three plain-language regimes:

  "trending"       -- price has moved persistently in one direction
  "ranging"        -- price is moving sideways, no persistent direction
  "high_volatility" -- price is swinging widely regardless of direction

This is intentionally simpler than paper_trading.market_state.classify()
(which drives real trade decisions and has finer-grained states like
breakout/structure). Regime detection here is a separate, display/filter-
only signal -- nothing in this module can open, close, or size a trade.

Heuristic (standard, well-known building blocks, nothing custom-invented):
  - ATR(14) as a % of price = volatility measure. Above
    HIGH_VOLATILITY_ATR_PCT -> "high_volatility" (checked first: a
    strongly volatile move can look "trending" on a slope alone, and
    volatility is the more actionable label for risk purposes).
  - 20-period moving-average slope (% change over the last 10 periods) =
    trend measure. Above TREND_SLOPE_PCT in either direction -> "trending".
  - Otherwise -> "ranging".
"""

from backtest_engine import concepts
from data_engine.resample import get_ohlcv

_TIMEFRAME = "1h"
_LOOKBACK_HOURS = 72
_MA_PERIOD = 20
_HIGH_VOLATILITY_ATR_PCT = 3.0
_TREND_SLOPE_PCT = 1.5


def classify_regime(exchange, symbol):
    """Returns {"regime", "atr_pct", "ma_slope_pct"} or None if there isn't
    enough data yet (degrades gracefully -- a newly-tracked symbol simply
    has no regime label rather than a misleading guess)."""
    import time
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - _LOOKBACK_HOURS * 3600 * 1000
    df = get_ohlcv(exchange, symbol, interval=_TIMEFRAME, start_ms=start_ms, end_ms=end_ms)
    if len(df) < _MA_PERIOD + 10:
        return None

    closes = df["close"]
    price = float(closes.iloc[-1])
    if price <= 0:
        return None

    atr = concepts.atr(df, 14)
    atr_pct = float(atr.iloc[-1] / price * 100) if atr.iloc[-1] else 0.0

    ma = closes.rolling(_MA_PERIOD).mean()
    ma_now = ma.iloc[-1]
    ma_prev = ma.iloc[-11] if len(ma) > 10 else ma.iloc[0]
    ma_slope_pct = float((ma_now - ma_prev) / ma_prev * 100) if ma_prev else 0.0

    if atr_pct >= _HIGH_VOLATILITY_ATR_PCT:
        regime = "high_volatility"
    elif abs(ma_slope_pct) >= _TREND_SLOPE_PCT:
        regime = "trending"
    else:
        regime = "ranging"

    return {"regime": regime, "atr_pct": round(atr_pct, 3), "ma_slope_pct": round(ma_slope_pct, 3)}


def classify_all(exchange, symbols):
    """Bulk version for a dashboard/filter view -- errors on one symbol
    never stop the others."""
    out = {}
    for symbol in symbols:
        try:
            result = classify_regime(exchange, symbol)
        except Exception:
            result = None
        if result:
            out[symbol] = result
    return out
