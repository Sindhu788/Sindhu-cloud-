"""Grand Master Prompt, Phase 4.6: Goal System -- a general, user-set
goal on a real live-trading metric (e.g. "reach 60% win rate", "reduce
drawdown below 8%"), DISTINCT from Challenge Mode (paper_trading/
challenge_mode.py), which is specifically a dollar-amount growth target
with pace tracking. This never affects trading -- purely a progress
display against numbers that already exist elsewhere.

Supported metrics are limited to ones with an honest, already-computed
current value -- no invented approximation for a metric this codebase
doesn't already track cleanly:
  - win_rate_pct: storage.get_paper_period_summary()["win_rate"] (all-time,
    or scoped to one strategy via storage.list_paper_strategy_stats)
  - net_pnl: the same summary's total_pnl
  - total_trades: the same summary's closed_trades
"""
import uuid
from datetime import datetime, timezone

from data_engine import storage

SUPPORTED_METRICS = ("win_rate_pct", "net_pnl", "total_trades")


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def create_goal(metric, target_value, comparison="gte", scope_strategy_id=None, label=None):
    if metric not in SUPPORTED_METRICS:
        raise ValueError(f"Unsupported metric '{metric}' -- must be one of {SUPPORTED_METRICS}")
    if comparison not in ("gte", "lte"):
        raise ValueError("comparison must be 'gte' or 'lte'")
    goal_id = uuid.uuid4().hex[:12]
    storage.create_user_goal(goal_id, metric, target_value, comparison, scope_strategy_id, label, _now_iso())
    return goal_id


def _current_value(metric, scope_strategy_id):
    if scope_strategy_id:
        stats = next((s for s in storage.list_paper_strategy_stats() if s["strategy_id"] == scope_strategy_id), None)
        if not stats:
            return None
        summary = {"win_rate": stats.get("win_rate", 0.0), "total_pnl": stats["total_pnl"],
                   "closed_trades": stats.get("closed_trades", 0)}
    else:
        summary = storage.get_paper_period_summary()
    return {
        "win_rate_pct": summary["win_rate"],
        "net_pnl": summary["total_pnl"],
        "total_trades": summary["closed_trades"],
    }[metric]


def _is_achieved(current, target, comparison):
    if current is None:
        return False
    return current >= target if comparison == "gte" else current <= target


def list_goals_with_progress(include_archived=False):
    goals = storage.list_user_goals(include_archived=include_archived)
    result = []
    for g in goals:
        current = _current_value(g["metric"], g["scope_strategy_id"])
        achieved = _is_achieved(current, g["target_value"], g["comparison"])
        if achieved and not g["achieved_at"]:
            storage.mark_goal_achieved(g["id"], _now_iso())
            g["achieved_at"] = _now_iso()
        result.append({**g, "current_value": current, "achieved": achieved})
    return result


def archive_goal(goal_id):
    storage.archive_user_goal(goal_id)
