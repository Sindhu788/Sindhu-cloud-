import time
import requests

_BASE_URL = "https://api.coingecko.com/api/v3"
_session = requests.Session()


def get_top_market_cap_coins(limit=200):
    """Coins ranked by market cap, highest first. Paginates in chunks of 100
    (CoinGecko's max per_page) since we may need to look past the top N to
    find enough that are actually listed on Binance."""
    coins = []
    page = 1
    per_page = 100
    while len(coins) < limit:
        resp = _session.get(
            f"{_BASE_URL}/coins/markets",
            params={
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": per_page,
                "page": page,
            },
            timeout=15,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        coins.extend(batch)
        page += 1
        time.sleep(1.5)  # be polite to the free public API
        if page > 5:
            break
    return coins[:limit]
