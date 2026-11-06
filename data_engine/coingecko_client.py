import json
import os
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

# Master plan V2 R1 (P5): one overall deadline for the whole top-coins fetch (all pages and retries), short connect/read
# timeouts, and the last good list kept on disk with its timestamp, so a CoinGecko outage (or a restart during one) never
# stalls the scanner: it uses the last good list and logs that once.
_DEADLINE_S = 20.0
_CONNECT_TIMEOUT_S = 5.0
_READ_TIMEOUT_S = 10.0
_DISK_KEEP = ("id", "symbol", "name", "market_cap_rank", "market_cap")


class DeadlineExceeded(requests.Timeout):
    """The top-coins fetch ran past _DEADLINE_S."""


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
    if one exists. The whole fetch has one deadline (_DEADLINE_S)."""
    now = time.monotonic()
    if (_cache["coins"] is not None and _cache["limit"] >= limit
            and now - _cache["fetched_at"] < _CACHE_TTL_SECONDS):
        return _cache["coins"][:limit]

    try:
        coins = _fetch_top_market_cap_coins(limit, deadline=time.monotonic() + _DEADLINE_S)
    except requests.RequestException as exc:
        # Master plan P5 follow-up: ANY network failure (not only 429) falls back to a stale list when one exists; the top-50 by
        # market cap barely changes between scans. V2 R1: then the last good list on disk. Without either the error is raised.
        have = _cache["coins"] is not None or bool(_load_disk_cache())
        _log_fallback(exc, have)
        if _cache["coins"] is not None:
            return _cache["coins"][:limit]
        disk = _load_disk_cache()
        if disk:
            _cache["limit"] = max(limit, len(disk))
            _cache["coins"] = disk
            _cache["fetched_at"] = now  # reuse for one TTL before trying the network again
            return disk[:limit]
        raise
    _cache["limit"] = limit
    _cache["coins"] = coins
    _cache["fetched_at"] = now
    _save_disk_cache(coins)
    return coins


def _disk_cache_path():
    try:
        from data_engine import paths
        return os.path.join(paths.CONFIG_DIR, "coingecko_top_coins_cache.json")
    except Exception:
        return None


def _save_disk_cache(coins):
    p = _disk_cache_path()
    if not p or not coins:
        return
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        slim = [{k: c.get(k) for k in _DISK_KEEP if k in c} for c in coins if isinstance(c, dict)]
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"saved_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "coins": slim}, f)
        os.replace(tmp, p)  # atomic
    except Exception:
        pass


def _load_disk_cache():
    p = _disk_cache_path()
    if not p:
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return list(json.load(f).get("coins") or [])
    except Exception:
        return None


def disk_cache_info():
    """For /health/details: when the last good list was saved and how many coins it has (no network)."""
    p = _disk_cache_path()
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        return {"saved_at_utc": d.get("saved_at_utc"), "coins": len(d.get("coins") or [])}
    except Exception:
        return None


def _log_fallback(exc, have_list=True):
    try:
        from paper_trading import log_dedup
        log_dedup.maybe_log(print, "coingecko-top-coins", exc,
                            f"[coingecko] top-coins fetch failed ({type(exc).__name__}); " + ("using the last good list" if have_list else "no saved list yet: the caller's fallback is used"), every=1800)
    except Exception:
        pass


def _fetch_top_market_cap_coins(limit, deadline=None):
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
            deadline=deadline,
        )
        if not batch:
            break
        coins.extend(batch)
        page += 1
        if len(coins) >= limit:
            break
        if deadline is not None and time.monotonic() + 1.5 > deadline:
            raise DeadlineExceeded("top-coins deadline reached between pages")
        time.sleep(1.5)  # be polite to the free public API
        if page > 5:
            break
    return coins[:limit]


_MAX_WAIT_S = 20.0          # master plan P5: one 429 pause is at most 20 s (Cloud log 6 Nov 01:43: a 139 s stall here) ...
_CALL_BUDGET_S = 45.0       # ... and all retries of one call together at most 45 s


def _get_with_retry(url, params, max_retries=3, sleep=None, deadline=None):
    sleep = sleep or time.sleep
    last_exc = None
    started = time.monotonic()
    waited = 0.0
    for attempt in range(max_retries):
        timeout = (_CONNECT_TIMEOUT_S, _READ_TIMEOUT_S)
        if deadline is not None:
            left = deadline - time.monotonic()
            if left <= 0.5:
                raise DeadlineExceeded("top-coins deadline reached")
            timeout = (min(_CONNECT_TIMEOUT_S, left), min(_READ_TIMEOUT_S, left))
        resp = _session.get(url, params=params, timeout=timeout)
        if resp.status_code == 429:
            last_exc = requests.HTTPError(f"429 Client Error: Too Many Requests for url: {resp.url}", response=resp)
            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if retry_after and retry_after.isdigit() else 5.0 * (attempt + 1)
            wait = min(wait, _MAX_WAIT_S)
            if max(time.monotonic() - started, waited) + wait > _CALL_BUDGET_S:
                break
            if deadline is not None and max(time.monotonic(), started + waited) + wait > deadline:
                break
            sleep(wait)
            waited += wait
            continue
        resp.raise_for_status()
        return resp.json()
    raise last_exc
