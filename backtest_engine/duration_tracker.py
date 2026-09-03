"""Session Time-Tracker (Grand Feature Expansion, Phase 3 Feature 14): how
long backtests actually take and where that processing time goes.

job_manager's in-memory job registry (sindhu_web/jobs/job_manager.py) is
capped at 200 entries and wiped on every restart -- fine for "is this
still running", useless for a durable time-tracking history. Backtest
batches, on the other hand, are permanent: backtest_batches.created_at is
set the moment a batch starts, and .updated_at is set to the exact
completion timestamp the instant storage.update_batch_status(..., "completed")
runs (data_engine/storage.py) -- their difference is a real, durable
duration with no new tracking instrumentation needed anywhere."""

from datetime import datetime

from data_engine import storage


def compute_duration_stats(limit=100):
    """Returns per-batch durations for the most recent COMPLETED batches
    plus aggregate stats. Skips a batch whose timestamps don't parse or
    whose duration comes out negative (clock skew/manual DB edit) rather
    than reporting a nonsense number."""
    batches = storage.list_recent_batches(limit=limit)
    durations = []
    for b in batches:
        if b["status"] != "completed":
            continue
        try:
            start = datetime.fromisoformat(b["created_at"])
            end = datetime.fromisoformat(b["updated_at"])
        except (ValueError, TypeError):
            continue
        seconds = (end - start).total_seconds()
        if seconds < 0:
            continue
        durations.append({
            "batch_id": b["batch_id"],
            "strategy_name": b.get("display_name") or b["strategy_name"],
            "duration_seconds": round(seconds, 1),
            "created_at": b["created_at"],
        })

    if not durations:
        return {"batches": [], "count": 0, "avg_duration_seconds": None,
                "total_time_spent_seconds": 0.0, "slowest": []}

    avg = sum(d["duration_seconds"] for d in durations) / len(durations)
    total = sum(d["duration_seconds"] for d in durations)
    slowest = sorted(durations, key=lambda d: d["duration_seconds"], reverse=True)[:5]

    return {
        "batches": durations, "count": len(durations),
        "avg_duration_seconds": round(avg, 1), "total_time_spent_seconds": round(total, 1),
        "slowest": slowest,
    }
