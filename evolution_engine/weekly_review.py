"""Automated Weekly Strategy Review (Grand Feature Expansion, Phase 6
Feature 13): a scheduled, plain-language summary of the week's EVOLUTION/
TUNING activity -- mutations, rollbacks, before/after metrics -- distinct
from paper_trading.weekly_report (trading performance only) and
paper_trading.monthly_report (also trading performance, 30-day window).
evolution_engine.history.compute_evolution_history() already aggregates
this exact data; it was only ever reachable on-demand, never delivered on
a schedule. Mirrors paper_trading.weekly_report's own established
generate/gate/scheduler/Telegram-send shape exactly."""

import json
from datetime import datetime, timezone, timedelta

from data_engine import storage, feature_toggles
from evolution_engine import history
from paper_trading import telegram_bot

REVIEW_INTERVAL_DAYS = 7


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def generate_weekly_review():
    now = datetime.now(timezone.utc)
    result = history.compute_evolution_history("week", now=now)

    lines = [
        f"Evolution Weekly Review -- {now.strftime('%Y-%m-%d')}",
        "",
        f"{result['strategies_evolved']} strategy lineage(s) evolved this week, "
        f"producing {result['generations_created']} new generation(s).",
    ]

    if result["finalized"] == 0:
        lines.append("None of this week's changes have enough real trades yet to be judged -- check back next week.")
    else:
        lines.append(
            f"{result['finalized']} of those have enough real trades to judge: "
            f"{result['improved']} improved and were kept, {result['rollbacks']} performed worse and were "
            f"automatically rolled back to the previous version, {result['pending']} still awaiting enough trades."
        )
        before, after = result["before"], result["after"]
        if before.get("win_rate") is not None and after.get("win_rate") is not None:
            lines.append(
                f"Average win rate across judged changes: {before['win_rate']}% -> {after['win_rate']}%."
            )
        if before.get("total_pnl") is not None and after.get("total_pnl") is not None:
            lines.append(
                f"Average net PnL across judged changes: ${before['total_pnl']:.2f} -> ${after['total_pnl']:.2f}."
            )

    if result["generations_created"] == 0:
        lines.append("Nothing evolved this week -- no lineage crossed a new 100-trade milestone yet.")

    report_text = "\n".join(lines)
    report_data = {
        "strategies_evolved": result["strategies_evolved"],
        "generations_created": result["generations_created"],
        "rollbacks": result["rollbacks"],
        "improved": result["improved"],
        "pending": result["pending"],
        "before": result["before"],
        "after": result["after"],
    }
    storage.save_evolution_weekly_report(result["since"], result["until"], json.dumps(report_data), report_text, _now_iso())
    return {"report_text": report_text, "report_data": report_data}


def maybe_generate_weekly_review():
    """Called periodically by the scheduler thread -- only generates a new
    review if 7+ days have passed since the last one (or none exists yet).
    Also sends it to Telegram, same as weekly_report.py -- the 7-day gate
    already prevents more than one send per week."""
    if not feature_toggles.is_enabled("evolution_weekly_review_enabled"):
        return None
    last = storage.get_latest_evolution_weekly_report()
    if last:
        last_dt = datetime.fromisoformat(last)
        if datetime.now(timezone.utc) - last_dt < timedelta(days=REVIEW_INTERVAL_DAYS):
            return None
    result = generate_weekly_review()
    if telegram_bot._master_enabled():
        ok, err = telegram_bot._raw_send(result["report_text"])
        storage.log_telegram_message(
            None, None, None, "evolution_weekly_review", result["report_text"], ok, err, _now_iso(),
        )
        result["telegram_sent"] = ok
        result["telegram_error"] = err
    return result


def start_evolution_weekly_review_scheduler_thread():
    """Runs once at server startup; checks every few hours whether a new
    review is due -- same shape as paper_trading.weekly_report's own
    start_weekly_report_scheduler_thread."""
    import threading
    import time
    from data_engine.logging_setup import log

    def _loop():
        while True:
            try:
                result = maybe_generate_weekly_review()
                if result:
                    log("[evolution-weekly-review] generated a new evolution weekly review")
            except Exception as e:
                log(f"[evolution-weekly-review] generation failed: {e!r}")
            time.sleep(6 * 3600)  # check every 6 hours; the 7-day gate above prevents over-generating

    threading.Thread(target=_loop, daemon=True).start()
