"""Batch 6, Task 1 -- Evolution History Timeline. A read-only reporting
view over data the Evolution Engine already recorded: evolution_comparisons
(one row per mutation that reached the 100-trade gate, Batch 1) and
bot_strategies (one row per generation, for the Generations-created count).

Never triggers evolution, never mutates a generation, never writes
anything -- pure aggregation over already-stored rows.
"""

from datetime import datetime, timedelta, timezone

from data_engine import storage

WINDOWS = {
    "week": 7,
    "15d": 15,
    "month": 30,
    "longer": 120,
}

_METRIC_KEYS = ("win_rate", "total_pnl", "avg_profit_factor", "max_drawdown_pct")


def _now():
    return datetime.now(timezone.utc)


def _window_bounds(window, now=None, offset_periods=0):
    """Returns (since_iso, until_iso) for `window`, optionally shifted back
    by `offset_periods` whole windows (offset_periods=1 -- the immediately
    PRECEDING period of the same length, for period-over-period
    comparison)."""
    if window not in WINDOWS:
        raise ValueError(f"unknown window: {window!r}")
    now = now or _now()
    days = WINDOWS[window]
    until = now - timedelta(days=days * offset_periods)
    since = until - timedelta(days=days)
    return since.isoformat(), until.isoformat()


def _avg(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 4) if values else None


def _aggregate_metrics(comparisons, side):
    """side: "before" or "after". Averages each of the 4 core metrics
    across every comparison that HAS a value for that side (after_json is
    None until a comparison is finalized -- excluded automatically since
    comp[side] is None in that case)."""
    result = {}
    for key in _METRIC_KEYS:
        result[key] = _avg([
            (comp[side] or {}).get(key) for comp in comparisons if comp[side] is not None
        ])
    return result


def compute_evolution_history(window, now=None, offset_periods=0):
    """The real numbers behind one time window. Returns:
    {
      "window": str, "since": iso, "until": iso,
      "strategies_evolved": int (distinct base_id with >=1 event in window),
      "generations_created": int (total evolution_comparisons rows -- a
          strategy can generate more than once in a window),
      "rollbacks": int, "finalized": int (verdict is not None),
      "improved": int, "pending": int (still awaiting enough trades to judge),
      "before": {...avg of the 4 core metrics across finalized comparisons...},
      "after": {...same, "after" side...},
      "comparisons": [...raw rows, for a detail table...],
    }"""
    since_iso, until_iso = _window_bounds(window, now=now, offset_periods=offset_periods)
    comparisons = storage.list_evolution_comparisons_between(since_iso, until_iso)

    finalized = [c for c in comparisons if c["verdict"] is not None]
    rollbacks = sum(1 for c in comparisons if c["rolled_back"])
    improved = sum(1 for c in finalized if c["verdict"] == "improved")

    return {
        "window": window, "since": since_iso, "until": until_iso,
        "strategies_evolved": len({c["base_id"] for c in comparisons}),
        "generations_created": len(comparisons),
        "rollbacks": rollbacks,
        "finalized": len(finalized),
        "improved": improved,
        "pending": len(comparisons) - len(finalized),
        "before": _aggregate_metrics(finalized, "before"),
        "after": _aggregate_metrics(finalized, "after"),
        "comparisons": comparisons,
    }


def compare_periods(window, now=None):
    """Period-over-period: this window vs the immediately preceding window
    of the same length (e.g. this month vs last month). Returns
    {"current": {...compute_evolution_history...}, "previous": {...}}."""
    return {
        "current": compute_evolution_history(window, now=now, offset_periods=0),
        "previous": compute_evolution_history(window, now=now, offset_periods=1),
    }
