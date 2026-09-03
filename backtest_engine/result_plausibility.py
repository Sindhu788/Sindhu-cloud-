"""Sanity Check Alert (Grand Feature Expansion, Phase 3 Feature 1): flags a
COMPLETED backtest result as suspiciously implausible -- near-0%/near-100%
win rate, an absurd average profit %, or an absurd trades-per-coin count --
before anyone treats it as real.

Distinct from backtest_engine/sanity_check.py, which runs BEFORE a full
backtest (a tiny sample run checking for a structural zero-trade bug that
would waste a full run). This runs AFTER a batch completes, checking
whether the numbers it actually produced are plausible at all. Purely
read-only reporting -- never blocks, retries, cancels, or modifies a
backtest; it only raises a dashboard alert (the existing paper_alerts
table/Alerts section, same one orphaned-position and other system alerts
already use) for a human to look at.
"""

from datetime import datetime, timezone

from backtest_engine.reports import quick_batch_summary
from data_engine import storage

MIN_SAMPLE_FOR_WIN_RATE_CHECK = 10
EXTREME_WIN_RATE_LOW = 2.0
EXTREME_WIN_RATE_HIGH = 98.0
EXTREME_PROFIT_PCT = 5000.0  # a 50x return from one backtest period is almost always a bug, not skill
EXTREME_TRADES_PER_SYMBOL = 5000  # this many re-entries on one coin in one backtest suggests a signal that never cools down

_ALWAYS_SINCE = "2000-01-01T00:00:00+00:00"  # "has this batch EVER been flagged" -- a completed backtest's numbers never change


def check_batch_plausibility(batch_id):
    """Returns {"plausible": bool, "flags": [str, ...], "summary": dict|None}.
    flags is empty both when nothing looks suspicious AND when there isn't
    enough data to judge either way -- never a false alarm on a tiny or
    still-running batch."""
    summary = quick_batch_summary(batch_id)
    if not summary or not summary.get("total_trades"):
        return {"plausible": True, "flags": [], "summary": summary}

    flags = []
    if summary["total_trades"] >= MIN_SAMPLE_FOR_WIN_RATE_CHECK:
        if summary["win_rate"] <= EXTREME_WIN_RATE_LOW:
            flags.append(
                f"Win rate is only {summary['win_rate']}% over {summary['total_trades']} trades -- "
                f"unusually close to always losing; worth checking for an inverted entry/exit condition "
                f"or a broken stop-loss."
            )
        elif summary["win_rate"] >= EXTREME_WIN_RATE_HIGH:
            flags.append(
                f"Win rate is {summary['win_rate']}% over {summary['total_trades']} trades -- unusually "
                f"close to always winning; worth checking for lookahead bias or a take-profit that can't "
                f"actually miss."
            )

    if summary.get("avg_profit_pct") is not None and abs(summary["avg_profit_pct"]) >= EXTREME_PROFIT_PCT:
        flags.append(
            f"Average profit is {summary['avg_profit_pct']}% -- an extreme return for one backtest period; "
            f"worth checking for a compounding or position-sizing bug rather than assuming real skill."
        )

    if summary.get("symbol_count") and summary["total_trades"] / summary["symbol_count"] >= EXTREME_TRADES_PER_SYMBOL:
        per_symbol = round(summary["total_trades"] / summary["symbol_count"], 1)
        flags.append(
            f"Averaging {per_symbol} trades per coin in this one backtest -- suspiciously high re-entry "
            f"frequency; worth checking for a signal that never properly resets or cools down."
        )

    return {"plausible": len(flags) == 0, "flags": flags, "summary": summary}


def sweep_recently_completed_batches(check_last_n=20):
    """Checks the most recently completed batches for implausible results,
    creating one paper_alerts entry the FIRST time a given batch is
    flagged -- never re-alerts the same batch twice (a completed
    backtest's numbers are immutable, so nothing here can change)."""
    now_iso = datetime.now(timezone.utc).isoformat()
    flagged = []
    for batch in storage.list_recent_batches(limit=check_last_n):
        if batch["status"] != "completed":
            continue
        if storage.get_recent_paper_alert("backtest_implausible_result", batch["batch_id"], _ALWAYS_SINCE):
            continue
        result = check_batch_plausibility(batch["batch_id"])
        if not result["plausible"]:
            label = batch.get("display_name") or batch["strategy_name"]
            message = f"{label} (batch {batch['batch_id']}): " + " ".join(result["flags"])
            storage.create_paper_alert(
                "backtest_implausible_result", batch["batch_id"], label, message, "warning", now_iso,
            )
            flagged.append(batch["batch_id"])
    return flagged


def start_plausibility_sweep_thread():
    """Runs once at server startup (local only -- backtests are a
    local-laptop-only feature, never mounted on the cloud runner). Same
    shape as sindhu_web.api.backup.start_auto_backup_thread."""
    import threading
    import time
    from data_engine.logging_setup import log

    def _loop():
        while True:
            try:
                flagged = sweep_recently_completed_batches()
                if flagged:
                    log(f"[sanity-check] flagged {len(flagged)} implausible backtest result(s): {flagged}")
            except Exception as e:
                log(f"[sanity-check] sweep failed: {e!r}")
            time.sleep(3600)  # hourly -- new batches complete far less often than that

    threading.Thread(target=_loop, daemon=True).start()
