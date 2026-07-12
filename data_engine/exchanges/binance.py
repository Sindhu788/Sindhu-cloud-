from data_engine import binance_client
from data_engine.exchanges.base import ExchangeClient


class BinanceClient(ExchangeClient):
    """Adapter around the existing, already-working binance_client module so
    it satisfies the common ExchangeClient interface. Behavior is unchanged
    from before multi-exchange support was added."""

    id = "binance"

    def get_tradeable_symbols(self, quote):
        info = binance_client.get_exchange_info()
        return {
            s["baseAsset"]: s["symbol"]
            for s in info["symbols"]
            if s["status"] == "TRADING"
            and s["quoteAsset"] == quote
            and s["isSpotTradingAllowed"]
        }

    def get_ohlcv(self, symbol, interval, since_ms=None, limit=1000):
        return binance_client.get_klines(
            symbol, interval, start_time_ms=since_ms, limit=limit
        )

    def get_tickers(self, quote):
        data = binance_client.get_ticker_24hr()
        result = {}
        for t in data:
            symbol = t["symbol"]
            if not symbol.endswith(quote):
                continue
            result[symbol] = {
                "price": float(t["lastPrice"]),
                "change_pct": float(t["priceChangePercent"]),
                "volume": float(t["quoteVolume"]),
            }
        return result
