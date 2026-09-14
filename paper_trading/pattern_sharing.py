"""Grand Master Batch, Phase 5 Item 7: cross-strategy pattern-sharing
suggestion, with MANDATORY manual approval before a pattern learned on
one strategy is ever applied to another.

Distinct from paper_trading.lesson_auto_apply, which only ever promotes
a pattern into an ACTIVE rule for the SAME strategy+coin+condition it
was learned from -- this module suggests taking an already-proven
pattern from strategy A and applying it to strategy B (a different
strategy trading the same coin), which never happens automatically
anywhere in this codebase until now, and even now only after an
explicit CEO approval recorded here.
"""

from datetime import datetime, timezone
import uuid

from data_engine import config as base_config, storage

_CLOUD_KEY = "cross_strategy_pattern_suggestions"
_FILE = "pattern_sharing.json"
_DEFAULTS = {"suggestions": []}


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _load():
    return base_config.load_persistent(_CLOUD_KEY, _FILE, _DEFAULTS)


def _save(data):
    base_config.save_persistent(_CLOUD_KEY, _FILE, data)


def generate_suggestions():
    """Scans every ACTIVE, already-proven pattern (paper_auto_lessons --
    real, Wilson-gate-cleared patterns lesson_auto_apply already promoted
    for their OWN strategy) and, for every OTHER enabled strategy that
    trades the same symbol but doesn't already have this exact pattern
    applied to itself, records a new pending suggestion. Never applies
    anything -- only ever proposes. Idempotent: re-running skips a
    (source, target, symbol, market_state, session) combo that already
    has a pending or decided suggestion, so re-running doesn't spam
    duplicates."""
    from backtest_engine import strategy_library

    active_patterns = storage.list_paper_auto_lessons(active_only=True)
    names_by_id = {m["id"]: m["name"] for m in strategy_library.list_all()}
    enabled_strategies = {
        sid: {"strategy_name": names_by_id.get(sid, sid), "supported_coins": cfg.get("supported_coins") or []}
        for sid, cfg in storage.list_paper_strategy_configs().items()
        if cfg.get("enabled")
    }

    data = _load()
    existing_keys = {
        (s["source_strategy_id"], s["target_strategy_id"], s["symbol"], s["market_state"], s["session"])
        for s in data["suggestions"]
    }
    now = _now_iso()
    new_suggestions = []
    for pattern in active_patterns:
        for target_id, target_row in enabled_strategies.items():
            if target_id == pattern["strategy_id"]:
                continue
            supported = target_row["supported_coins"]
            if supported and pattern["symbol"] not in supported:
                continue  # this strategy is restricted to coins that don't include this pattern's coin
            key = (pattern["strategy_id"], target_id, pattern["symbol"], pattern["market_state"], pattern["session"])
            if key in existing_keys:
                continue
            already_has_own = any(
                p["strategy_id"] == target_id and p["symbol"] == pattern["symbol"]
                and p["market_state"] == pattern["market_state"] and p["session"] == pattern["session"]
                for p in active_patterns
            )
            if already_has_own:
                continue
            suggestion = {
                "id": uuid.uuid4().hex[:12], "status": "pending", "suggested_at": now,
                "source_strategy_id": pattern["strategy_id"], "source_strategy_name": pattern["strategy_name"],
                "target_strategy_id": target_id, "target_strategy_name": target_row.get("strategy_name", target_id),
                "symbol": pattern["symbol"], "market_state": pattern["market_state"], "session": pattern["session"],
                "influence": pattern["influence"], "sample_size": pattern["sample_size"], "win_rate": pattern["win_rate"],
                "explanation": (
                    f"{pattern['strategy_name'] or pattern['strategy_id']}'s proven pattern on {pattern['symbol']} "
                    f"during {pattern['market_state']} markets in the {pattern['session']} session "
                    f"({pattern['win_rate']:.0f}% win rate over {pattern['sample_size']} trades) could apply to "
                    f"{target_row.get('strategy_name', target_id)} too, which also trades {pattern['symbol']} "
                    f"but doesn't have this pattern yet."
                ),
            }
            new_suggestions.append(suggestion)
            existing_keys.add(key)

    if new_suggestions:
        data["suggestions"].extend(new_suggestions)
        _save(data)
    return new_suggestions


def list_suggestions(status=None):
    suggestions = _load()["suggestions"]
    if status:
        suggestions = [s for s in suggestions if s["status"] == status]
    return suggestions


def approve_suggestion(suggestion_id, now_iso=None):
    """The ONLY path that actually applies a shared pattern -- always an
    explicit, one-at-a-time CEO action, never automatic. Applies it via
    the exact same storage.save_paper_auto_lesson() lesson_auto_apply
    itself uses, so an approved suggestion becomes a real, normal active
    lesson for the target strategy -- indistinguishable from one it
    would have earned on its own, just credited with its real source."""
    data = _load()
    suggestion = next((s for s in data["suggestions"] if s["id"] == suggestion_id), None)
    if suggestion is None:
        raise ValueError(f"unknown suggestion_id: {suggestion_id}")
    if suggestion["status"] != "pending":
        raise ValueError(f"suggestion {suggestion_id} is already {suggestion['status']}")

    now_iso = now_iso or _now_iso()
    storage.save_paper_auto_lesson(
        suggestion["target_strategy_id"], suggestion["target_strategy_name"], suggestion["symbol"],
        suggestion["market_state"], suggestion["session"], suggestion["influence"],
        suggestion["sample_size"], suggestion["win_rate"],
        f"(Shared from {suggestion['source_strategy_name'] or suggestion['source_strategy_id']}, "
        f"CEO-approved) {suggestion['explanation']}",
        now_iso,
    )
    suggestion["status"] = "approved"
    suggestion["decided_at"] = now_iso
    _save(data)
    return suggestion


def reject_suggestion(suggestion_id, now_iso=None):
    data = _load()
    suggestion = next((s for s in data["suggestions"] if s["id"] == suggestion_id), None)
    if suggestion is None:
        raise ValueError(f"unknown suggestion_id: {suggestion_id}")
    suggestion["status"] = "rejected"
    suggestion["decided_at"] = now_iso or _now_iso()
    _save(data)
    return suggestion
