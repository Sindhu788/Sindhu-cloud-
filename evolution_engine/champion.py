"""A.7 -- Champion Engine. Recomputes, from data that already exists, which
strategy/lesson/coin/session/timeframe/market-condition/generation is
currently performing best. Read-only over paper_positions/bot_strategies/
bot_lessons/paper_strategy_performance/paper_lesson_performance -- it never
writes to any of those, only appends a new row per category to
champion_records (storage.save_champion), so recomputing champions can
never modify a user-imported strategy or a user-written lesson, and never
loses a previous champion (see A.9).

Every "best" here also considers BOT strategies/lessons where those exist,
but falls back to the wider paper_strategy_performance/paper_lesson_performance
tables (which include everything currently paper-trading, BOT or user) when
no BOT data exists yet -- this is a pure READ for display purposes, not a
modification of whatever it reads.
"""

from data_engine import storage

MIN_SAMPLE_SIZE = 5
HISTORY_LOOKBACK = 3000


def _best_bucket(history, key_fn, min_sample=MIN_SAMPLE_SIZE):
    buckets = {}
    for p in history:
        key = key_fn(p)
        if not key:
            continue
        b = buckets.setdefault(key, {"trades": 0, "wins": 0, "pnl": 0.0})
        b["trades"] += 1
        if p.get("is_win"):
            b["wins"] += 1
        b["pnl"] += p.get("pnl") or 0.0
    scored = []
    for key, b in buckets.items():
        if b["trades"] < min_sample:
            continue
        win_rate = b["wins"] / b["trades"] * 100.0
        composite = win_rate * 0.5 + min(b["pnl"], 1000.0) * 0.05
        scored.append((composite, key, b, win_rate))
    if not scored:
        return None
    scored.sort(key=lambda x: -x[0])
    return scored[0]


def recompute_champions(now_iso):
    """Recomputes every champion category and appends a fresh
    champion_records row for each one that has enough data to judge.
    Returns {category: value} for whichever categories were updated this
    call."""
    results = {}

    bot_strategies = [s for s in storage.list_bot_strategies(status="active", limit=5000)
                       if s.get("evolution_score") is not None]
    if bot_strategies:
        best = max(bot_strategies, key=lambda s: s["evolution_score"])
        storage.save_champion("strategy", best["id"], best["evolution_score"],
                               {"name": best["name"], "generation": best["generation"], "source": "bot_strategies"}, now_iso)
        storage.save_champion("generation", str(best["generation"]), best["evolution_score"],
                               {"strategy_id": best["id"], "source": "bot_strategies"}, now_iso)
        results["strategy"] = best["id"]
        results["generation"] = best["generation"]
    else:
        perf = storage.list_paper_strategy_performance()
        if perf:
            best = perf[0]  # already ORDER BY score DESC
            storage.save_champion("strategy", best["strategy_id"], best["score"],
                                   {"name": best["strategy_name"], "source": "paper_strategy_performance"}, now_iso)
            results["strategy"] = best["strategy_id"]

    bot_lessons = [l for l in storage.list_bot_lessons(status="active", limit=5000) if l.get("confidence") is not None]
    if bot_lessons:
        best = max(bot_lessons, key=lambda l: l["confidence"])
        storage.save_champion("lesson", best["id"], best["confidence"],
                               {"title": best["title"], "source": "bot_lessons"}, now_iso)
        results["lesson"] = best["id"]
    else:
        lesson_perf = storage.list_paper_lesson_performance()
        if lesson_perf:
            best = lesson_perf[0]
            storage.save_champion("lesson", best["lesson_id"], best["score"],
                                   {"title": best["lesson_title"], "source": "paper_lesson_performance"}, now_iso)
            results["lesson"] = best["lesson_id"]

    history = storage.list_closed_paper_positions(limit=HISTORY_LOOKBACK)  # strategy_id=None -> every book
    for category, key_fn in (
        ("coin", lambda p: p.get("symbol")),
        ("session", lambda p: p.get("session")),
        ("timeframe", lambda p: p.get("timeframe")),
        ("market_condition", lambda p: p.get("market_state")),
    ):
        best = _best_bucket(history, key_fn)
        if best is None:
            continue
        composite, key, b, win_rate = best
        storage.save_champion(category, key, round(composite, 2),
                               {"trades": b["trades"], "win_rate": round(win_rate, 2), "pnl": round(b["pnl"], 2)}, now_iso)
        results[category] = key

    return results


def current_champions():
    """Every category's most recent champion, for the Evolution Dashboard."""
    return storage.list_current_champions()
