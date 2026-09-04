"""Phase 1.2: AI-assisted idea generation -- AI is used ONLY to suggest
which already-scored concept-combination is worth trying next; it NEVER
invents concepts, builds the candidate, or makes a trading decision, and it
is never called during backtesting or paper-trading. This is the project's
core "AI is only a temporary teacher" rule, applied here at the narrowest
possible point: re-ranking a short list combination_scorer.py already
computed from real data, nothing more.

Distinct from sindhu_strategy/ai_builder.py (which asks AI to invent an
ENTIRE strategy from scratch) -- this module's prompt never asks AI to
design conditions/stop-loss/take-profit, only to pick among combos this
engine already scored deterministically. If AI is unavailable or fails,
discovery_cycle.py falls back to the plain best-scored combo
(select_next_combination's own fallback path below) -- the engine works
without AI, just less refined, exactly as Phase 1.2 implies.
"""

import json
import re
from datetime import datetime, timezone

from ai_integration import config as ai_config
from ai_integration.providers import get_provider
from data_engine import storage

AI_ENDPOINT = "/ai/self-learning-combo-ranking"
TOP_N_CONSIDERED = 10

_SYSTEM_PROMPT = """You are helping prioritize which trading-concept combination to
backtest next, from a list already ranked by real historical performance data.
You are NOT designing a strategy and NOT making any trading decision -- only
picking which already-scored candidate combination is worth spending a real
backtest on next, and saying briefly why.

Respond with ONLY a single JSON object, no prose, no markdown fences, in
exactly this shape:
{"chosen_index": 0, "reason": "one short sentence"}
`chosen_index` MUST be an index into the list you were given (0-based)."""


def _extract_json(text):
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("AI response did not contain a JSON object")
    return json.loads(match.group(0))


def _fallback_choice(candidates, reason):
    return {"chosen_index": 0, "combo": candidates[0], "reason": reason, "ai_used": False}


def select_next_combination(candidates):
    """candidates: combination_scorer.score_combinations()'s output, already
    best-first. Returns {chosen_index, combo, reason, ai_used}.

    Deliberately a single provider call, no fallback loop across providers
    (same shape as sindhu_strategy.ai_builder's "one attempt, no retry"
    rule) -- if it fails, this is simply "no AI suggestion this cycle," not
    something to retry with a different provider."""
    if not candidates:
        return None
    shortlist = candidates[:TOP_N_CONSIDERED]

    chain = ai_config.provider_fallback_chain()
    if not chain:
        return _fallback_choice(shortlist, "no AI provider is configured/enabled -- using the top-scored combination")

    provider_name = chain[0]
    settings = ai_config.get_provider_settings(provider_name)
    provider = get_provider(provider_name, settings)

    listing = "\n".join(
        f"{i}. combo={c['dna_combo']} avg_score={c['avg_score']} sample_size={c['sample_size']} "
        f"best_coins={[bc['symbol'] for bc in c['best_coins'][:3]]}"
        for i, c in enumerate(shortlist)
    )
    now_iso = datetime.now(timezone.utc).isoformat()
    result = provider.chat(
        f"Here are the top {len(shortlist)} scored candidate combinations:\n{listing}\n\n"
        "Which index is worth trying next, and why?",
        system=_SYSTEM_PROMPT,
    )
    storage.save_ai_usage_log(
        provider_name, settings.get("model"), AI_ENDPOINT,
        "success" if result.ok else "failed", now_iso,
        tokens_in=result.tokens_in, tokens_out=result.tokens_out,
        latency_ms=result.latency_ms, error_message=None if result.ok else result.error,
    )
    if not result.ok:
        return _fallback_choice(shortlist, f"AI provider call failed ({result.error}) -- using the top-scored combination")

    try:
        parsed = _extract_json(result.text)
        idx = int(parsed["chosen_index"])
        if not (0 <= idx < len(shortlist)):
            raise ValueError(f"chosen_index {idx} out of range")
    except Exception as e:
        return _fallback_choice(shortlist, f"AI response could not be parsed ({e}) -- using the top-scored combination")

    return {
        "chosen_index": idx, "combo": shortlist[idx],
        "reason": str(parsed.get("reason") or "").strip() or "AI suggestion (no reason given)",
        "ai_used": True,
    }
