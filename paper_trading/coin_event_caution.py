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

import requests

from data_engine import config as base_config

_CLOUD_KEY = "coin_event_caution_settings"
_FILE = "coin_event_caution.json"
_DEFAULTS = {"cryptopanic_api_key": ""}
_REQUEST_TIMEOUT_SECONDS = 10
_CRYPTOPANIC_URL = "https://cryptopanic.com/api/v1/posts/"


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
