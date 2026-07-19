"""B.1/B.2 -- the daily SINDHU Strategy generation cycle. Exactly 11
candidates per calendar date (UTC), hard-capped, of which at most 1 may be
AI-assisted -- both limits enforced by data_engine.storage's
daily_generation_log (try_reserve_ai_generation_call / candidates_generated),
not by counting in Python, so re-invoking this function twice in the same
day can never exceed either limit.
"""

import threading
from datetime import datetime, timezone

from data_engine import storage
from evolution_engine import generation_manager
from sindhu_strategy import ai_builder, deterministic_builder

DAILY_CAP = 11
_SCHEDULER_CHECK_INTERVAL_SECONDS = 3600  # hourly is plenty for a once-a-day cap


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _today(now_iso):
    return now_iso[:10]  # ISO date prefix, e.g. "2026-07-19"


def generate_daily_candidates(now_iso=None, timeframe="5m"):
    """Idempotent-per-day: if today's cap is already reached (whether from
    an earlier call today or a resumed/duplicate trigger), returns []
    immediately rather than generating anything more. Returns the list of
    bot_strategy ids created this call (0-11)."""
    now_iso = now_iso or _now_iso()
    today = _today(now_iso)
    created = []

    log = storage.get_daily_generation(today)
    if log["candidates_generated"] >= DAILY_CAP:
        return created

    # -- B.2: the single AI-assisted candidate, at most once per day. --
    if log["ai_calls_used"] == 0 and storage.try_reserve_ai_generation_call(today, now_iso):
        try:
            config_dict, dna_tags, reason = ai_builder.build_ai_candidate()
            sid = generation_manager.create_new_strategy_lineage(
                config_dict.get("name") or "SINDHU AI Candidate", config_dict, dna_tags,
                "sindhu_ai", True, reason, now_iso,
            )
            created.append(sid)
            storage.increment_daily_candidates_generated(today, now_iso, by=1)
        except Exception:
            # The day's one AI attempt happened and failed (ai_builder
            # already logged it to ai_usage_log before raising) -- the slot
            # stays reserved, no retry today (try_reserve_ai_generation_call's
            # guarantee). The missing candidate is simply made up by an
            # extra deterministic one below so the day still totals 11.
            pass

    # -- B.2: fill every remaining slot with zero-AI deterministic candidates. --
    index = 0
    while True:
        log = storage.get_daily_generation(today)
        if log["candidates_generated"] >= DAILY_CAP:
            break
        config_dict, dna_tags, reason = deterministic_builder.build_candidate(index, timeframe=timeframe)
        sid = generation_manager.create_new_strategy_lineage(
            config_dict.get("name") or f"SINDHU Deterministic Candidate #{index + 1}",
            config_dict, dna_tags, "sindhu_deterministic", False, reason, now_iso,
        )
        created.append(sid)
        storage.increment_daily_candidates_generated(today, now_iso, by=1)
        index += 1

    return created


def today_candidates(now_iso=None):
    """Every bot_strategy created today via this generator (both origins),
    for the SINDHU Strategy page's daily view."""
    now_iso = now_iso or _now_iso()
    today = _today(now_iso)
    all_gen1 = [s for s in storage.list_bot_strategies(status="active", limit=5000) if s["generation"] == 1]
    return [s for s in all_gen1 if s["created_at"][:10] == today and s["origin"] in ("sindhu_ai", "sindhu_deterministic")]


# ---- background scheduler: unlike evolution_engine (manually started/
# stopped by the CEO), the daily 11-candidate cycle is meant to run on its
# own every day without anyone toggling it -- so this is a simple always-on
# daemon thread, the same shape as backup.start_auto_backup_thread(),
# started once from sindhu_web/server.py's lifespan. Each iteration just
# calls generate_daily_candidates(), which is itself a safe no-op once
# today's 11 already exist, so an hourly check interval is both cheap and
# always eventually catches a fresh day. ----

_scheduler_thread = None
_scheduler_stop = threading.Event()


def _scheduler_loop():
    while not _scheduler_stop.is_set():
        try:
            generate_daily_candidates()
        except Exception:
            pass  # next hourly check tries again; a transient failure today never blocks any other day
        _scheduler_stop.wait(_SCHEDULER_CHECK_INTERVAL_SECONDS)


def start_daily_scheduler_thread():
    global _scheduler_thread
    if _scheduler_thread and _scheduler_thread.is_alive():
        return
    _scheduler_stop.clear()
    _scheduler_thread = threading.Thread(target=_scheduler_loop, daemon=True)
    _scheduler_thread.start()
