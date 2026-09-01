"""AI provider settings -- persisted the same way as every other SINDHU
setting: a JSON file under data/config/, via the existing
data_engine.config.load_or_seed / save_config helpers. No new persistence
mechanism, no database table for settings (matches app_settings.json,
paper_trading_settings.json, etc.)."""

import os

from data_engine import config as base_config

_SETTINGS_FILE = "ai_settings.json"

# Lightweight cloud runner support: the real ai_settings.json (with the
# CEO's already-configured Groq key) lives only on the local laptop and is
# not part of the curated cloud database or migrated anywhere -- a fresh
# Railway deploy starts with no AI provider configured at all, and this
# runner mounts no Settings page to enter one. GROQ_API_KEY, if set, seeds
# the very first save of ai_settings.json (data_engine.config.load_or_seed's
# existing "defaults only apply until the file exists" behavior) so AI
# Trade Review works immediately after deploy using the SAME key already
# configured locally, pasted once as an environment variable. Local laptop
# behavior is unchanged when the env var is unset.
_ENV_API_KEY_SEEDS = {"groq": "GROQ_API_KEY"}

SUPPORTED_PROVIDERS = ["claude", "groq", "openai", "gemini", "deepseek"]

_DEFAULT_MODELS = {
    "claude": "claude-sonnet-5",
    "groq": "openai/gpt-oss-120b",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.0-flash",
    "deepseek": "deepseek-chat",
}

_DEFAULT_PROVIDER_SETTINGS = {
    "api_key": "",
    "model": None,          # filled from _DEFAULT_MODELS per provider below
    "temperature": 0.3,
    "max_tokens": 4096,
    "timeout": 30,
    "retry_count": 2,
    "enabled": False,
    "last_test_status": "not_configured",   # not_configured | ok | error
    "last_test_message": "",
    "last_test_at": None,
    # Usage Monitor: quotas/cost are CEO-editable, None/0 = not tracked.
    # Never hardcoded from public pricing pages here -- prices change and
    # this system shouldn't silently assume stale numbers are still true.
    "daily_quota": None,
    "monthly_quota": None,
    "cost_per_1k_input": 0.0,
    "cost_per_1k_output": 0.0,
}


def _default_settings():
    providers = {}
    active_provider = None
    for name in SUPPORTED_PROVIDERS:
        entry = dict(_DEFAULT_PROVIDER_SETTINGS)
        entry["model"] = _DEFAULT_MODELS[name]
        env_var = _ENV_API_KEY_SEEDS.get(name)
        if env_var and os.environ.get(env_var):
            entry["api_key"] = os.environ[env_var]
            entry["enabled"] = True
            active_provider = name
        providers[name] = entry
    return {"active_provider": active_provider, "providers": providers}


def load_settings():
    """Returns the full settings dict, seeding the file on first run.
    Merges in any newly-added provider defaults so an older ai_settings.json
    (from before a new provider was added) still works without migration."""
    defaults = _default_settings()
    raw = base_config.load_or_seed(_SETTINGS_FILE, defaults)
    providers = raw.get("providers", {})
    for name in SUPPORTED_PROVIDERS:
        if name not in providers:
            entry = dict(_DEFAULT_PROVIDER_SETTINGS)
            entry["model"] = _DEFAULT_MODELS[name]
            providers[name] = entry
        else:
            merged = dict(_DEFAULT_PROVIDER_SETTINGS)
            merged["model"] = _DEFAULT_MODELS[name]
            merged.update(providers[name])
            providers[name] = merged
    raw["providers"] = providers
    raw.setdefault("active_provider", None)
    return raw


def save_settings(settings):
    base_config.save_config(_SETTINGS_FILE, settings)


def get_provider_settings(provider):
    settings = load_settings()
    if provider not in settings["providers"]:
        raise ValueError(f"Unknown AI provider: {provider}")
    return settings["providers"][provider]


def update_provider_settings(provider, **fields):
    settings = load_settings()
    if provider not in settings["providers"]:
        raise ValueError(f"Unknown AI provider: {provider}")
    entry = settings["providers"][provider]
    for key, value in fields.items():
        if value is not None and key in entry:
            entry[key] = value
    save_settings(settings)
    return entry


def set_enabled(provider, enabled):
    return update_provider_settings(provider, enabled=enabled)


def set_active_provider(provider):
    settings = load_settings()
    if provider is not None and provider not in settings["providers"]:
        raise ValueError(f"Unknown AI provider: {provider}")
    settings["active_provider"] = provider
    save_settings(settings)


def record_test_result(provider, status, message, now_iso):
    return update_provider_settings(
        provider, last_test_status=status, last_test_message=message, last_test_at=now_iso,
    )


def mask_key(key):
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "*" * (len(key) - 8) + key[-4:]


def active_provider_name():
    """The provider to use for AI-assisted import, or None if none is both
    set active and enabled with a key configured -- callers treat None as
    'use the rule-based-only path'."""
    settings = load_settings()
    name = settings.get("active_provider")
    if not name:
        return None
    entry = settings["providers"].get(name)
    if not entry or not entry.get("enabled") or not entry.get("api_key"):
        return None
    return name


def provider_fallback_chain():
    """Smart Provider Switching order: the CEO's chosen active_provider
    tried first (if it's actually usable), then every other enabled +
    configured provider in the default priority order (Claude primary,
    Groq secondary, OpenAI optional, then Gemini/DeepSeek). Returns only
    providers that are enabled AND have an API key -- an empty list means
    'no usable AI provider right now', which callers treat as Offline Mode."""
    settings = load_settings()
    active = settings.get("active_provider")
    usable = [
        name for name in SUPPORTED_PROVIDERS
        if settings["providers"].get(name, {}).get("enabled") and settings["providers"][name].get("api_key")
    ]
    ordered = []
    if active and active in usable:
        ordered.append(active)
    for name in usable:
        if name not in ordered:
            ordered.append(name)
    return ordered
