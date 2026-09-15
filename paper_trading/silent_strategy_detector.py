"""Grand Master Batch #2, Phase 4.6: Silent Strategy Detector -- flags any
ENABLED strategy that hasn't opened a single position in a long time as
needing review (it may be technically broken: a config error, an
exchange/symbol mismatch, a filter that always rejects it, etc.). Purely
read-only, same boundary as every other analysis module in this project --
never disables or pauses a strategy itself, only reports.
"""

from datetime import datetime, timezone

from data_engine import storage

DEFAULT_MIN_DAYS_SILENT = 14


def _now():
    return datetime.now(timezone.utc)


def _parse_iso(value):
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def detect_silent_strategies(min_days_silent=DEFAULT_MIN_DAYS_SILENT):
    """Returns a list of {strategy_id, days_silent, last_activity_at (or
    None if it has NEVER traded at all)}, sorted worst (longest silent)
    first. Only considers strategies with an explicit enabled=True config
    row -- a deliberately disabled/paused strategy being silent is
    expected, not a fault to flag."""
    configs = storage.list_paper_strategy_configs()
    last_activity = storage.get_last_activity_by_strategy()
    now = _now()

    flagged = []
    for strategy_id, cfg in configs.items():
        if not cfg.get("enabled"):
            continue
        last_at_iso = last_activity.get(strategy_id)
        last_at = _parse_iso(last_at_iso)
        if last_at is None:
            # Enabled but has NEVER opened a single position -- since
            # activation, whenever that was (updated_at, the config row's
            # own timestamp, is the closest real record of that). Always
            # worth flagging regardless of min_days_silent -- there is no
            # "recent enough" reading of zero trades ever.
            updated_at = _parse_iso(cfg.get("updated_at"))
            days_silent = (now - updated_at).days if updated_at else None
            flagged.append({
                "strategy_id": strategy_id, "last_activity_at": None,
                "days_silent": days_silent, "reason": "enabled but has never opened a single position",
            })
            continue
        days_silent = (now - last_at).days
        if days_silent >= min_days_silent:
            flagged.append({
                "strategy_id": strategy_id, "last_activity_at": last_at_iso,
                "days_silent": days_silent,
                "reason": f"no new position opened in {days_silent} days",
            })

    flagged.sort(key=lambda f: (f["days_silent"] if f["days_silent"] is not None else 10**9), reverse=True)
    return flagged
