"""Grand Master Batch #2, Phase 4.7: Cross-Exchange Price Sanity Check --
before a signal reaches Telegram, cross-check its price against a SECOND
exchange to rule out a single-source data glitch (a bad tick, a stale
websocket, a temporary exchange-side bug) being mistaken for a real
market move. Reuses the exact same exchange-client mechanism every other
live-price read in this codebase already uses (data_engine.exchanges.
registry) -- no new data source.

Deliberately wired only at the Telegram-send point (paper_trading.
telegram_bot.send_signal_for_position), not into every paper-trading tick's
internal candidate evaluation (paper_trading.risk_manager.evaluate) -- that
runs far more often (every strategy, every coin, every ~60s tick), and
adding a second exchange's live API call there would multiply outbound
API traffic for comparatively little benefit, since by the time a
candidate is about to be sent it has already survived every other filter.
"""

from data_engine import config as base_config
from data_engine.exchanges.registry import get_exchange_client

# The two exchanges this project actually supports today (see
# data_engine/config.py's exchanges.json default and its cloud-mode
# fallback) -- picks whichever one ISN'T the primary as the cross-check
# source.
_KNOWN_EXCHANGES = ["binance", "bybit"]


def _other_exchange(primary):
    for ex in _KNOWN_EXCHANGES:
        if ex != primary:
            return ex
    return None


def cross_exchange_check(primary_exchange, symbol, primary_price, max_deviation_pct=1.0):
    """Returns (ok: bool, reason: str|None, secondary_price: float|None).
    Never blocks when the primary price is missing, when there's no known
    second exchange, or when the second exchange's price genuinely
    couldn't be fetched (network blip, symbol not listed there) -- same
    "don't block on missing data" convention as every other gate in this
    codebase; this only blocks when it has a REAL, fetched second price
    that meaningfully disagrees with the first."""
    if primary_price is None:
        return True, None, None
    other = _other_exchange(primary_exchange)
    if not other:
        return True, None, None

    try:
        client = get_exchange_client(other)
        coins_cfg = base_config.load_or_seed("coins.json", base_config.DEFAULTS["coins.json"])
        tickers = client.get_tickers(coins_cfg["quote_asset"])
        ticker = tickers.get(symbol)
        secondary_price = ticker["price"] if ticker else None
    except Exception:
        secondary_price = None

    if secondary_price is None:
        return True, None, None

    deviation_pct = abs(primary_price - secondary_price) / primary_price * 100.0
    if deviation_pct > max_deviation_pct:
        return False, (
            f"price on {primary_exchange} (${primary_price:g}) disagrees with {other} (${secondary_price:g}) "
            f"by {deviation_pct:.2f}% -- withheld as a possible single-source data glitch"
        ), secondary_price
    return True, None, secondary_price
