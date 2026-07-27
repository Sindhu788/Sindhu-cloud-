"""Strategy Graveyard (Confidence & Signal Quality Group, item 9): a
permanent, never-deleted record of exactly why a strategy was effectively
abandoned, so a future import that resembles it can be warned. Nothing
here deletes or disables a strategy -- burial is a RECORD, not an action;
the strategy itself keeps existing in the library untouched.
"""

from datetime import datetime, timezone

from data_engine import storage
from backtest_engine import strategy_library as lib
from paper_trading import insights

# A strategy is only buried once its problem is well past the pause
# threshold (drawdown_guard.py's default of 7) -- burial is a much bigger,
# permanent statement than a temporary pause, so it deserves a stricter,
# separately-documented bar.
BURIAL_STREAK_THRESHOLD = 10
MIN_SHARED_CONCEPTS_FOR_WARNING = 2


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def bury_if_abandoned(strategy_id, strategy_name):
    """Checked after Drawdown Protection re-evaluates a strategy (see
    drawdown_guard.evaluate_strategy) -- if it's currently paused AND its
    losing streak has grown well past the pause bar, records a permanent
    graveyard entry. Idempotent: a strategy already buried is never
    re-buried (storage.is_strategy_buried short-circuits)."""
    if storage.is_strategy_buried(strategy_id):
        return None
    paused, pause_reason, _ = storage.is_strategy_paused(strategy_id)
    if not paused:
        return None
    streak = insights.compute_streak(strategy_id)
    if streak["type"] != "loss" or streak["count"] < BURIAL_STREAK_THRESHOLD:
        return None

    try:
        cfg = lib.load(strategy_id)
        concepts = sorted(set(cfg.concepts_used)) if hasattr(cfg, "concepts_used") and cfg.concepts_used else []
    except Exception:
        concepts = []

    detail = (f"Paused by Drawdown Protection ({pause_reason}) and never recovered -- "
              f"reached {streak['count']} consecutive losses, well past the normal pause bar.")
    storage.bury_strategy(strategy_id, strategy_name, "repeated_drawdown_pause", detail, concepts, _now_iso())
    return detail


def check_similarity_warnings(concepts_used):
    """Called when a NEW strategy is being reviewed/imported -- compares its
    concepts against every buried strategy's concepts and returns a plain-
    language warning for any with meaningful overlap. Never blocks the
    import; purely informational, exactly like every other warning system
    in this project (Correlation Warning, etc.)."""
    if not concepts_used:
        return []
    new_set = set(concepts_used)
    warnings = []
    for g in storage.list_graveyard():
        shared = new_set & set(g["concepts_used"])
        if len(shared) >= MIN_SHARED_CONCEPTS_FOR_WARNING:
            warnings.append({
                "strategy_name": g["strategy_name"],
                "shared_concepts": sorted(shared),
                "reason": g["reason_detail"],
                "message": (f"This resembles \"{g['strategy_name']}\", which was retired: {g['reason_detail']} "
                            f"(shared: {', '.join(sorted(shared))})"),
            })
    return warnings
