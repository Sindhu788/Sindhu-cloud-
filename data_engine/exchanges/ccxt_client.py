import time

import ccxt

from data_engine.exchanges.base import ExchangeClient
from data_engine.config import MAX_RETRIES


class CCXTClient(ExchangeClient):
    """Generic exchange client backed by the ccxt library. Works for any
    ccxt exchange id (okx, bybit, bitget, gate, ...) using only public
    endpoints -- no API keys needed for OHLCV history.

    ccxt's unified fetch_ohlcv only returns (timestamp, open, high, low,
    close, volume) -- it doesn't expose close_time/quote_volume/trade count
    the way Binance's raw REST klines do. Those three fields are
    approximated here (close_time from the timeframe's duration,
    quote_volume from volume*close, trades left at 0) so the shared storage
    schema still applies across every exchange; Binance itself still stores
    exact values via its own adapter.
    """

    def __init__(self, exchange_id):
        self.id = exchange_id
        self._exchange = getattr(ccxt, exchange_id)({"enableRateLimit": True})
        self._markets_loaded = False

    def _ensure_markets(self):
        if not self._markets_loaded:
            self._retry(self._exchange.load_markets)
            self._markets_loaded = True

    def _retry(self, fn, *args, **kwargs):
        last_err = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return fn(*args, **kwargs)
            except (ccxt.NetworkError, ccxt.ExchangeNotAvailable, ccxt.RequestTimeout) as e:
                last_err = e
                time.sleep(2 * attempt)
            except ccxt.RateLimitExceeded as e:
                last_err = e
                time.sleep(5 * attempt)
        raise RuntimeError(f"{self.id}: request failed after {MAX_RETRIES} retries: {last_err!r}")

    def get_tradeable_symbols(self, quote):
        self._ensure_markets()
        result = {}
        for market in self._exchange.markets.values():
            if not market.get("spot"):
                continue
            if market.get("quote") != quote:
                continue
            if market.get("active") is False:
                continue
            result[market["base"]] = market["symbol"]
        return result

    def get_ohlcv(self, symbol, interval, since_ms=None, limit=1000):
        raw = self._retry(
            self._exchange.fetch_ohlcv, symbol, timeframe=interval, since=since_ms, limit=limit
        )
        if not raw:
            return []

        duration_ms = ccxt.Exchange.parse_timeframe(interval) * 1000
        rows = []
        for open_time, o, h, l, c, v in raw:
            close_time = open_time + duration_ms - 1
            quote_volume = (v or 0.0) * (c or 0.0)
            rows.append((open_time, o, h, l, c, v or 0.0, close_time, quote_volume, 0))
        return rows

    def get_tickers(self, quote):
        # Bug fix, 2026-09-07 (found while switching the cloud default to
        # bybit for the Binance-451 fix): fetch_tickers() with NO symbols
        # argument returns whatever market type the exchange treats as its
        # own default -- confirmed live on bybit, that default is
        # PERPETUAL FUTURES (keys like "BTC/USDT:USDT"), not spot, even
        # though get_tradeable_symbols() above correctly filters to spot-
        # only markets. The old code's `symbol.endswith(f"/{quote}")`
        # check then matched ZERO of those keys (a perp key ends with
        # ":USDT", not "/USDT"), so this silently returned an EMPTY dict
        # on bybit -- no error, just no live prices, which is exactly the
        # shape of bug that shows up as a dashboard stuck on empty/loading
        # placeholders. Fixed by explicitly requesting only real spot
        # symbols (same market.get("spot") filter as get_tradeable_symbols
        # above) instead of trusting fetch_tickers()'s un-scoped default.
        self._ensure_markets()
        spot_symbols = [
            m["symbol"] for m in self._exchange.markets.values()
            if m.get("spot") and m.get("quote") == quote and m.get("active") is not False
        ]
        if not spot_symbols:
            return {}
        raw = self._retry(self._exchange.fetch_tickers, spot_symbols)
        result = {}
        for symbol, t in raw.items():
            if not symbol.endswith(f"/{quote}"):
                continue
            result[symbol] = {
                "price": t.get("last"),
                "change_pct": t.get("percentage"),
                "volume": t.get("quoteVolume"),
            }
        return result
