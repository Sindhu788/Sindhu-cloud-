"""AI Trade Review (Additional Features, B4): after a trade closes,
optionally makes AT MOST ONE AI call to write a short, plain-language
review of that specific trade -- reusing the exact same provider
connection/fallback-chain the AI import pipeline already uses
(ai_integration.providers/config), no new AI integration built. Clearly
optional: OFF by default (uses AI tokens), toggled in Settings.
"""

from datetime import datetime, timezone

from data_engine import storage, config as base_config
from ai_integration import config as ai_config
from ai_integration import providers as ai_providers
from paper_trading import insights

_SETTINGS_KEY = "ai_trade_review_settings"
_DEFAULTS = {"enabled": False}


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def is_enabled():
    return base_config.load_or_seed(_SETTINGS_KEY + ".json", _DEFAULTS).get("enabled", False)


def set_enabled(enabled):
    base_config.save_config(_SETTINGS_KEY + ".json", {"enabled": bool(enabled)})


def _build_prompt(closed_position):
    pnl = closed_position.get("pnl") or 0.0
    outcome = "won" if pnl > 0 else "lost" if pnl < 0 else "broke even on"
    reason = insights.humanize_reason(closed_position.get("entry_reason"))
    return (
        f"A trading strategy just closed a trade. Write ONE short sentence (max 30 words), "
        f"plain language, no jargon, explaining WHY this outcome likely happened, for someone "
        f"with no trading background. Facts: strategy {outcome} this trade on "
        f"{closed_position.get('symbol')}, direction {closed_position.get('direction')}, "
        f"entry reason: {reason}, exit reason: {closed_position.get('exit_reason')}, "
        f"market condition at the time: {closed_position.get('market_state')}, "
        f"result: {pnl:.2f} ({closed_position.get('pnl_pct', 0):.2f}%)."
    )


def review_trade(closed_position):
    """At most one AI call for this position (storage's UNIQUE constraint
    on position_id + get_trade_review's own check both guard against a
    duplicate call if this is somehow invoked twice). Returns None if
    disabled, already reviewed, or no AI provider is currently usable --
    never raises, this must never break a real trade close."""
    if not is_enabled():
        return None
    position_id = closed_position["id"]
    if storage.get_trade_review(position_id):
        return None

    chain = ai_config.provider_fallback_chain()
    if not chain:
        return None  # no usable provider configured -- degrades gracefully, no error surfaced mid-trade-close

    prompt = _build_prompt(closed_position)
    for provider_name in chain:
        try:
            settings = ai_config.get_provider_settings(provider_name)
            provider = ai_providers.get_provider(provider_name, settings)
            result = provider.chat(prompt)
            if result.ok and result.text.strip():
                text = result.text.strip()
                storage.save_trade_review(position_id, text, provider_name, _now_iso())
                return {"review_text": text, "provider": provider_name}
        except Exception:
            continue
    return None
