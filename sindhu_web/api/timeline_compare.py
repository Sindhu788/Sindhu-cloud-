"""Grand Master Prompt, Phase 4.8/4.14: Timeline Compare / Quick Compare --
a single reusable current-vs-previous-period comparison, built on the
exact same storage.get_paper_period_summary() every other analytics view
already uses. One implementation, usable from any page (matches this
project's own precedent: /api/evolution/history/compare already does the
identical current/previous shape, just scoped to Evolution only).
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException

from data_engine import storage

router = APIRouter()

_WINDOWS = {"today": timedelta(days=1), "week": timedelta(days=7), "month": timedelta(days=30)}


@router.get("/api/timeline-compare")
def get_timeline_compare(window: str = "today", strategy_id: str = None):
    """window: 'today' (vs yesterday), 'week' (vs last 7 days), or
    'month' (vs the 30 days before that) -- all fixed-length windows
    ending now, not calendar-aligned, so "this week" always means "the
    last 7 days" consistently regardless of what day it is today."""
    if window not in _WINDOWS:
        raise HTTPException(400, f"window must be one of {list(_WINDOWS)}")
    span = _WINDOWS[window]
    now = datetime.now(timezone.utc)
    current_start = now - span
    previous_start = current_start - span

    if strategy_id:
        def summary_for(since, until):
            stats = storage.list_paper_strategy_stats(since.isoformat(), until.isoformat())
            row = next((s for s in stats if s["strategy_id"] == strategy_id), None)
            return {"closed_trades": row["closed_trades"] if row else 0,
                    "total_pnl": row["total_pnl"] if row else 0.0,
                    "win_rate": row["win_rate"] if row else 0.0}
    else:
        def summary_for(since, until):
            s = storage.get_paper_period_summary(since.isoformat(), until.isoformat())
            return {"closed_trades": s["closed_trades"], "total_pnl": s["total_pnl"], "win_rate": s["win_rate"]}

    current = summary_for(current_start, now)
    previous = summary_for(previous_start, current_start)
    delta = {k: round(current[k] - previous[k], 2) for k in current}

    return {"window": window, "current": current, "previous": previous, "delta": delta}
