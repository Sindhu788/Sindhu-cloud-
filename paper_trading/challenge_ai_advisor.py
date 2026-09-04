"""Master Task 3, Phase 2.21: AI-Assisted Full-System Explanation Layer.

AI is used ONLY to turn already-computed real numbers into a plain-language
explanation -- it never decides whether a target is realistic (that's
challenge_mode.py's/challenge_analysis.py's own math), never touches
risk_pct/position sizing/trading behavior, and is never called during
backtesting or paper-trading execution. Same safe, narrow shape as
self_learning_engine/ai_advisor.py: one provider call, a real-data-grounded
prompt, and a safe non-AI fallback (the existing honest_note-style text)
if no provider is configured or the call fails.
"""

from datetime import datetime, timezone

from ai_integration import config as ai_config
from ai_integration.providers import get_provider
from data_engine import storage

AI_ENDPOINT = "/ai/challenge-mode-explanation"

_SYSTEM_PROMPT = """You are explaining, in plain simple language, whether a trading
challenge target is realistic. You are NOT deciding whether it is realistic --
that has ALREADY been decided from real historical data, which is given to you
below. Your only job is to explain WHY, in plain language a beginner with no
trading background can understand, referencing the specific real numbers you
were given (strategies, coins, win rates, pace numbers). Never invent a number
that was not given to you. Keep it to 3-5 short sentences.

Respond with ONLY a single JSON object, no prose, no markdown fences:
{"explanation": "..."}"""


def _fallback_explanation(progress, difficulty):
    realistic = progress.get("realistic")
    if realistic is None:
        return (
            "Abhi tak paper trading mein koi real trade band nahi hua, isliye is target ko "
            "system ki real history se compare nahi kiya ja sakta."
        )
    if realistic:
        return (
            f"Yeh target ({difficulty}) system ki real demonstrated pace "
            f"({progress.get('real_demonstrated_daily_rate_pct')}%/din) ke mutabiq mumkin lagta hai, "
            f"lekin koi guarantee nahi hai -- asal nateeja market par depend karta hai."
        )
    return (
        f"Yeh target abhi {difficulty} category mein hai -- zaroori pace "
        f"({progress.get('required_daily_rate_pct')}%/din) system ke real demonstrated pace "
        f"({progress.get('real_demonstrated_daily_rate_pct')}%/din) se kaafi zyada hai kisi bhi "
        f"mojooda strategy ke through."
    )


def explain(progress, difficulty, best_worst_likely=None):
    """progress: challenge_mode.compute_progress()'s (or challenge_multi.
    compute_progress_for's) real dict. difficulty: challenge_analysis.
    difficulty_rating()'s label. best_worst_likely: optional
    challenge_analysis.best_worst_likely_range()'s dict, included in the
    prompt when available for a richer, still 100% real-data-grounded
    explanation.

    Returns {"explanation": str, "ai_used": bool}. Never raises."""
    chain = ai_config.provider_fallback_chain()
    if not chain:
        return {"explanation": _fallback_explanation(progress, difficulty), "ai_used": False}

    provider_name = chain[0]
    settings = ai_config.get_provider_settings(provider_name)
    provider = get_provider(provider_name, settings)

    facts = [
        f"Required daily pace: {progress.get('required_daily_rate_pct')}%",
        f"System's real demonstrated daily pace: {progress.get('real_demonstrated_daily_rate_pct')}%",
        f"Real closed trades this pace is based on: {progress.get('closed_trades_used_for_baseline')}",
        f"Difficulty rating: {difficulty}",
        f"Currently ahead of pace: {progress.get('ahead_of_pace')}",
    ]
    if best_worst_likely and best_worst_likely.get("best_case"):
        facts.append(
            f"Best real combination: {best_worst_likely['best_case']['strategy_name']} on "
            f"{best_worst_likely['best_case']['symbol']} ({best_worst_likely['best_case']['daily_rate_pct']}%/day)"
        )
        if best_worst_likely.get("worst_case"):
            facts.append(
                f"Worst real combination considered: {best_worst_likely['worst_case']['strategy_name']} on "
                f"{best_worst_likely['worst_case']['symbol']} ({best_worst_likely['worst_case']['daily_rate_pct']}%/day)"
            )

    now_iso = datetime.now(timezone.utc).isoformat()
    result = provider.chat(
        "Real data:\n" + "\n".join(facts) + "\n\nExplain plainly why this target is or isn't realistic.",
        system=_SYSTEM_PROMPT,
    )
    storage.save_ai_usage_log(
        provider_name, settings.get("model"), AI_ENDPOINT,
        "success" if result.ok else "failed", now_iso,
        tokens_in=result.tokens_in, tokens_out=result.tokens_out,
        latency_ms=result.latency_ms, error_message=None if result.ok else result.error,
    )
    if not result.ok:
        return {"explanation": _fallback_explanation(progress, difficulty), "ai_used": False}

    import json
    import re
    match = re.search(r"\{.*\}", result.text, re.DOTALL)
    if not match:
        return {"explanation": _fallback_explanation(progress, difficulty), "ai_used": False}
    try:
        parsed = json.loads(match.group(0))
        explanation = str(parsed.get("explanation") or "").strip()
        if not explanation:
            raise ValueError("empty explanation")
    except Exception:
        return {"explanation": _fallback_explanation(progress, difficulty), "ai_used": False}

    return {"explanation": explanation, "ai_used": True}
