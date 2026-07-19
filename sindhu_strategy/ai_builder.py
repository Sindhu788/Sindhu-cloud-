"""B.2 -- the single AI-assisted daily candidate. Reuses the exact same AI
provider primitive (ai_integration.providers.AIProvider.chat) and the exact
same AI-dict -> StrategyConfig sanitization pipeline
(ai_integration.strategy_builder.build_strategy_config, which already runs
sync_concepts_used + _repair_structural_stop internally) that AI-assisted
strategy IMPORTS use -- nothing new is invented for validation, only the
generation prompt itself is new.

Makes exactly ONE provider call, with no fallback loop across providers --
deliberately different from deep_understanding._call_provider_chain (which
tries the next provider only on failure): B.2 requires "a single AI call"
full stop, so if this one attempt fails, sindhu_strategy.generator treats
that as "no AI candidate today" rather than trying a second provider.
"""

import json
import re
from datetime import datetime, timezone

from ai_integration import config as ai_config
from ai_integration.providers import get_provider
from ai_integration.strategy_builder import build_strategy_config
from ai_integration.schema import KNOWN_SESSIONS
from backtest_engine.validator import _KNOWN_INDICATORS
from data_engine import storage
from evolution_engine import dna as dna_module

AI_ENDPOINT = "/ai/sindhu-strategy-generation"

_SYSTEM_PROMPT = f"""You are a professional quantitative trading strategy designer. Invent ONE
genuinely original, creative trading strategy candidate from scratch -- not
a copy of a well-known named strategy, and not extracted from any document.
Combine 2-4 concepts in a way a purely mechanical recombination of
historical stats would be unlikely to arrive at on its own.

You may ONLY use these exact concept/indicator names (do not invent new
ones): {sorted(_KNOWN_INDICATORS)}
Sessions you may use: {KNOWN_SESSIONS}

Respond with ONLY a single JSON object, no prose, no markdown fences, in
exactly this shape:
{{
  "name": "short strategy name",
  "timeframes": {{"entry": "5m"}},
  "concepts_used": ["concept1", "concept2"],
  "entry_conditions": [{{"type": "concept", "name": "concept1", "direction": "bullish"}}],
  "confirmation_conditions": [],
  "exit_conditions": [],
  "stop_loss": {{"type": "structure"}},
  "take_profit": {{"type": "rr", "value": 2.0}},
  "risk_pct": 1.0,
  "risk_reward": 2.0,
  "session_filter": [],
  "trend_filter": null,
  "day_filter": [],
  "breakeven_at_rr": null
}}"""


def _extract_json(text):
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("AI response did not contain a JSON object")
    return json.loads(match.group(0))


def build_ai_candidate():
    """Returns (config_dict, dna_tags, reason). Raises on any failure
    (no configured provider, network error, unparseable response) --
    generator.py's caller treats an exception here as "the day's one AI
    attempt happened and did not produce a candidate," never as licence to
    retry with a different provider."""
    chain = ai_config.provider_fallback_chain()
    if not chain:
        raise RuntimeError("no AI provider is configured/enabled -- cannot build the AI-assisted candidate today")
    provider_name = chain[0]
    settings = ai_config.get_provider_settings(provider_name)
    provider = get_provider(provider_name, settings)

    now_iso = datetime.now(timezone.utc).isoformat()
    result = provider.chat("Invent one original trading strategy candidate as specified.", system=_SYSTEM_PROMPT)
    storage.save_ai_usage_log(
        provider_name, settings.get("model"), AI_ENDPOINT,
        "success" if result.ok else "failed", now_iso,
        tokens_in=result.tokens_in, tokens_out=result.tokens_out,
        latency_ms=result.latency_ms, error_message=None if result.ok else result.error,
    )
    if not result.ok:
        raise RuntimeError(f"AI provider call failed: {result.error}")

    ai_strategy = _extract_json(result.text)
    config = build_strategy_config(ai_strategy, ai_strategy.get("name") or "SINDHU AI Candidate", result.text)
    config_dict = config.to_dict()
    dna_tags = dna_module.extract_dna(config)
    reason = f"AI-generated via {provider_name} (single call, endpoint={AI_ENDPOINT})"
    return config_dict, dna_tags, reason
