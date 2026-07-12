"""Live Market step: keeps the shortlisted coins' 1m candles fresh by
reusing the exact same incremental fetch the Data Engine's downloader
already implements (data_engine.downloader.download_symbol) -- same
klines_1m table, same resume-from-last-candle logic, no duplicated fetch
code and no duplicated data.
"""

from data_engine.downloader import download_symbol
from data_engine.logging_setup import log as default_log


def refresh_coins(exchange_client, symbols, log=default_log):
    """Fetches only the newest candles (usually 0-2 per coin, since ticks
    run every ~60s) for each shortlisted symbol. Errors on one coin never
    stop the others."""
    updated = []
    for symbol in symbols:
        try:
            added = download_symbol(exchange_client, symbol, log=lambda *_: None)
            if added:
                updated.append(symbol)
        except Exception as e:
            log(f"[paper-trading] live feed error for {symbol}: {e!r}")
    return updated
