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


def pick_top_symbols(exchange_client, n=NUM_COINS, quote=QUOTE_ASSET):
    """Top n real cryptocurrencies (ranked by CoinGecko market cap) that also
    trade as a spot pair against `quote` on `exchange_client`. Market cap
    ranking (rather than raw 24h volume) avoids pulling in stablecoins,
    tokenized stocks/commodities, and volume-spiking new listings."""
    tradeable = _filter_tradeable(exchange_client.get_tradeable_symbols(quote))

    coins = get_top_market_cap_coins(limit=max(n * 4, 200))
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
