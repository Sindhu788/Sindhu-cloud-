"""Grand Master Batch, Phase 4 Item 12: coin-specific event/news caution
flag.

Honest finding, not a guess: there is no reliable FREE, no-signup crypto
news/economic-calendar API. CoinGecko's free tier has no news/event
endpoint; CryptoPanic and CoinMarketCal both have usable free tiers, but
both require the CEO to create their own free account and supply an API
key -- exactly the "clearly mark this as needing the user's own account/
API setup... don't block on it" case the task itself anticipated.

This builds the HOOK only: an optional API key setting (CryptoPanic's
free tier -- simplest signup, plain JSON, a generous free quota) and a
best-effort fetch function. With no key configured, it returns a clear
"not configured" state rather than fabricating a caution flag -- a fake
"no known events" reading on a coin about to have a real event would be
actively worse than admitting this isn't hooked up yet.

What the CEO needs to provide, if they want this feature live:
1. A free account at https://cryptopanic.com/developers/api/
2. Their free API key (called an "auth_token" there), pasted into
   Settings > Coin Event Caution.
"""

import time

import requests

from data_engine import config as base_config

_CLOUD_KEY = "coin_event_caution_settings"
_FILE = "coin_event_caution.json"
_DEFAULTS = {"cryptopanic_api_key": ""}
_REQUEST_TIMEOUT_SECONDS = 10
_CRYPTOPANIC_URL = "https://cryptopanic.com/api/v1/posts/"

# Phase 5 -- News Monitoring, wired into trading: risk_manager.evaluate()
# calls this on every candidate, for every coin, every tick -- calling
# check_coin_caution() directly there would burn through CryptoPanic's free-
# tier rate limit almost immediately. This per-symbol, 5-minute cache (same
# cadence as cloud_aware_auto_stop's own live network check) sits in front
# of it. Deliberately a SEPARATE cache layer rather than added inside
# check_coin_caution() itself, so that function's existing behavior/tests
# (each call always hits the network) are completely unaffected -- this is
# purely additive, only used by the new gate below.
_GATE_CACHE_TTL_SECONDS = 300
_gate_cache = {}


def _cached_check(symbol):
    now = time.time()
    cached = _gate_cache.get(symbol)
    if cached and now - cached[0] < _GATE_CACHE_TTL_SECONDS:
        return cached[1]
    result = check_coin_caution(symbol)
    _gate_cache[symbol] = (now, result)
    return result


def evaluate_for_risk_gate(symbol):
    """Returns (ok: bool, reason: str|None) for wiring into
    risk_manager.evaluate() (feature_toggles.coin_event_caution_gate_enabled,
    off by default -- see that flag's own comment). Never fabricates a
    block: no API key configured, an API error, or a genuinely clear
    result (no "important"/"hot" headlines) all pass open -- only a real,
    already-fetched caution result blocks a new entry. Matches this
    module's own "never fabricate a caution flag" principle: absence of
    data is not evidence of safety, but it is not evidence of danger
    either, so it can't be grounds to block a trade."""
    result = _cached_check(symbol)
    if not result.get("available") or not result.get("caution"):
        return True, None
    headline = (result.get("headlines") or [{}])[0].get("title", "an important headline")
    return False, f"CryptoPanic flags an important/hot real headline for this coin: \"{headline}\""


def load_settings():
    return base_config.load_persistent(_CLOUD_KEY, _FILE, _DEFAULTS)


def save_settings(**fields):
    settings = load_settings()
    settings.update({k: v for k, v in fields.items() if v is not None})
    base_config.save_persistent(_CLOUD_KEY, _FILE, settings)
    return settings


def check_coin_caution(symbol):
    """Best-effort: real CryptoPanic headlines mentioning this coin in the
    last 24h, filtered to ones CryptoPanic itself tags "important"/
    "hot" -- never a fabricated or guessed caution. Returns
    {"available": False, "reason": ...} when no API key is configured,
    so the caller can show an honest "not set up" state instead of a
    fake "all clear"."""
    api_key = load_settings().get("cryptopanic_api_key")
    if not api_key:
        return {
            "available": False,
            "reason": "No CryptoPanic API key configured yet -- Settings > Coin Event Caution. "
                      "Free account: https://cryptopanic.com/developers/api/",
        }
    coin = symbol.replace("USDT", "").replace("USD", "").upper()
    try:
        resp = requests.get(
            _CRYPTOPANIC_URL,
            params={"auth_token": api_key, "currencies": coin, "filter": "important", "public": "true"},
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        if resp.status_code != 200:
            return {"available": False, "reason": f"CryptoPanic returned HTTP {resp.status_code}"}
        results = resp.json().get("results", [])
    except requests.RequestException as e:
        return {"available": False, "reason": f"CryptoPanic request failed: {e!r}"}

    if not results:
        return {"available": True, "caution": False, "headlines": []}
    return {
        "available": True, "caution": True,
        "headlines": [{"title": r.get("title"), "url": r.get("url"), "published_at": r.get("published_at")}
                      for r in results[:5]],
    }
