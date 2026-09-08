import re

from data_engine.coingecko_client import get_top_market_cap_coins
from data_engine.config import NUM_COINS, QUOTE_ASSET

# Leveraged tokens, stablecoins, and commodity-backed tokens we don't want in
# a "50 coins" crypto list, plus anything whose ticker isn't plain latin
# alphanumerics (rules out oddities like a symbol using Chinese characters as
# its base asset). Applied the same way regardless of which exchange the
# symbol came from.
_LEVERAGED_SUFFIXES = ("UP", "DOWN", "BULL", "BEAR")
_TICKER_RE = re.compile(r"^[A-Z0-9]+$")
_NON_CRYPTO_ASSETS = {
    "USDC", "FDUSD", "TUSD", "USDP", "DAI", "BUSD", "EUR", "GBP", "TRY", "AEUR",
    "RLUSD", "USD1", "USDE", "PYUSD", "USDX", "FRAX", "GUSD", "LUSD", "USTC",
    "USDS", "BFUSD",  # stablecoins
    "XAUT", "PAXG",  # gold-backed, not crypto price action
}


def _filter_tradeable(raw_tradeable):
    return {
        base: symbol
        for base, symbol in raw_tradeable.items()
        if not base.endswith(_LEVERAGED_SUFFIXES)
        and base not in _NON_CRYPTO_ASSETS
        and _TICKER_RE.match(base)
    }


def pick_top_symbols(exchange_client, n=NUM_COINS, quote=QUOTE_ASSET, tradeable=None):
    """Top n real cryptocurrencies (ranked by CoinGecko market cap) that also
    trade as a spot pair against `quote` on `exchange_client`. Market cap
    ranking (rather than raw 24h volume) avoids pulling in stablecoins,
    tokenized stocks/commodities, and volume-spiking new listings.

    `tradeable` can be passed in already-fetched (e.g. by the cloud exchange
    failover's own health-check call in data_engine.exchanges.registry) to
    avoid a second, redundant get_tradeable_symbols() call against the
    exchange every tick.

    Urgent bug fix, 2026-09-08: CoinGecko's free tier confirmed live to
    sustain 429 (Too Many Requests) from Render's shared/datacenter IP for
    40+ minutes straight, with zero successful calls in that whole window
    -- caching alone (data_engine.coingecko_client's own fix) cannot help
    when there has never even been ONE successful call to cache. Rather
    than leave every tick permanently stuck with zero symbols whenever
    CoinGecko's free tier is unavailable, a failure here falls back to
    ranking the exact same already-tradeable/filtered symbols by the
    exchange's own real 24h quote volume instead of market cap -- a
    different but still real, still honest liquidity signal, not a
    fabricated one."""
    if tradeable is None:
        tradeable = exchange_client.get_tradeable_symbols(quote)
    tradeable = _filter_tradeable(tradeable)

    try:
        coins = get_top_market_cap_coins(limit=max(n * 4, 200))
    except Exception:
        return _pick_top_symbols_by_exchange_volume(exchange_client, tradeable, n, quote)

    seen_base = set()
    picked = []
    for coin in coins:
        base = coin["symbol"].upper()
        if base in seen_base or base in _NON_CRYPTO_ASSETS or base not in tradeable:
            continue
        seen_base.add(base)
        picked.append(tradeable[base])
        if len(picked) >= n:
            break

    return picked


def _pick_top_symbols_by_exchange_volume(exchange_client, tradeable, n, quote):
    """CoinGecko-unavailable fallback -- see pick_top_symbols's own
    docstring. Never raises: an exchange ticker-fetch failure here just
    means no symbols this tick (same as CoinGecko being unavailable used
    to mean before this fix), not a second exception replacing the first."""
    try:
        tickers = exchange_client.get_tickers(quote)
    except Exception:
        return []
    ranked = sorted(
        (symbol for symbol in tradeable.values() if tickers.get(symbol, {}).get("volume")),
        key=lambda symbol: tickers[symbol]["volume"],
        reverse=True,
    )
    return ranked[:n]
