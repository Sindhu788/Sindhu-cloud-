class ExchangeClient:
    """Common interface every exchange client implements, so the rest of the
    data engine (symbol picking, downloading, resampling) never needs to
    know which exchange it's talking to."""

    id = "base"

    def get_tradeable_symbols(self, quote):
        """Return {base_asset: exchange_symbol} for actively trading spot
        pairs against `quote`. No crypto-specific filtering (stablecoins,
        leveraged tokens, etc.) happens here -- that's applied once, the
        same way for every exchange, in data_engine.symbols."""
        raise NotImplementedError

    def get_ohlcv(self, symbol, interval, since_ms=None, limit=1000):
        """Return a list of raw kline rows, each shaped as:
        (open_time_ms, open, high, low, close, volume, close_time_ms, quote_volume, trades)
        ordered oldest-first, starting at or after since_ms."""
        raise NotImplementedError

    def get_tickers(self, quote):
        """Return {symbol: {"price": float, "change_pct": float, "volume": float}}
        for every actively trading pair against `quote` -- one call, used by
        the Market page instead of per-symbol requests."""
        raise NotImplementedError
