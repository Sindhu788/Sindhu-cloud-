import time
import requests

_BASE_URL = "https://api.coingecko.com/api/v3"
_session = requests.Session()

# Urgent bug fix, 2026-09-08 (continued): once the exchange-geo-block fix
# let paper-trading ticks actually reach this call, EVERY tick started
# hitting "429 Client Error: Too Many Requests" here instead -- confirmed
# live in the cloud engine's tick logs. CoinGecko's free tier rate-limits
# shared/datacenter IPs (Render's included) far more aggressively than a
# residential one, and this was being called fresh on every single tick
# (every ~60s) for a ranking that barely changes minute to minute. Caching
# the result for _CACHE_TTL_SECONDS cuts real call volume by roughly the
# same factor as the cache lifetime vs. the tick interval, which is enough
# headroom to stay under the free tier's limit in practice.
_CACHE_TTL_SECONDS = 300
_cache = {"limit": None, "coins": None, "fetched_at": 0.0}


def get_top_market_cap_coins(limit=200):
    """Coins ranked by market cap, highest first. Paginates in chunks of 100
    (CoinGecko's max per_page) since we may need to look past the top N to
    find enough that are actually listed on Binance.

    Cached for _CACHE_TTL_SECONDS (a market-cap ranking large enough to
    satisfy `limit` from a still-fresh previous call is reused as-is,
    never re-fetched just because `limit` differs slightly) -- see the bug
    fix note above. On a 429 (rate limited), retries a few times honoring
    the server's Retry-After header when present, and falls back to a
    still-usable stale cache rather than failing the whole tick outright
    if one exists."""
    now = time.monotonic()
    if (_cache["coins"] is not None and _cache["limit"] >= limit
            and now - _cache["fetched_at"] < _CACHE_TTL_SECONDS):
        return _cache["coins"][:limit]

    try:
        coins = _fetch_top_market_cap_coins(limit)
    except requests.RequestException:
        # Master plan P5 follow-up: ANY network failure (not only 429) falls back to a stale list when one exists; the top-50 by
        # market cap barely changes between scans. Without a cached list the error is raised as before.
        if _cache["coins"] is not None:
            return _cache["coins"][:limit]
        raise
    _cache["limit"] = limit
    _cache["coins"] = coins
    _cache["fetched_at"] = now
    return coins


def _fetch_top_market_cap_coins(limit):
    coins = []
    page = 1
    per_page = 100
    while len(coins) < limit:
        batch = _get_with_retry(
            f"{_BASE_URL}/coins/markets",
            params={
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": per_page,
                "page": page,
            },
        )
        if not batch:
            break
        coins.extend(batch)
        page += 1
        time.sleep(1.5)  # be polite to the free public API
        if page > 5:
            break
    return coins[:limit]


_MAX_WAIT_S = 20.0          # master plan P5: one 429 pause is at most 20 s (Cloud log 6 Nov 01:43: a 139 s stall here) ...
_CALL_BUDGET_S = 45.0       # ... and all retries of one call together at most 45 s


def _get_with_retry(url, params, max_retries=3, sleep=None):
    sleep = sleep or time.sleep
    last_exc = None
    started = time.monotonic()
    waited = 0.0
    for attempt in range(max_retries):
        resp = _session.get(url, params=params, timeout=15)
        if resp.status_code == 429:
            last_exc = requests.HTTPError(f"429 Client Error: Too Many Requests for url: {resp.url}", response=resp)
            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if retry_after and retry_after.isdigit() else 5.0 * (attempt + 1)
            wait = min(wait, _MAX_WAIT_S)
            if max(time.monotonic() - started, waited) + wait > _CALL_BUDGET_S:
                break
            sleep(wait)
            waited += wait
            continue
        resp.raise_for_status()
        return resp.json()
    raise last_exc
