"""Batch 7, Task 5: Daily Honest Report -- once a day, a plain Roman Urdu
Telegram summary assembled ENTIRELY from data already computed elsewhere
(paper_positions via storage.get_paper_period_summary/list_paper_strategy_stats,
telegram_message_log via storage.list_telegram_send_texts_since, and
paper_trading.insights' existing streak detector) -- no new calculation,
no AI call. Every metric that has no data yet says so plainly rather
than showing a blank or a misleading zero, matching the project's
standing "never fabricate a number" rule.

Reuses telegram_message_log itself (trigger_type='daily_report') as the
send audit trail -- no new table needed.
"""

from datetime import datetime, timezone

from backtest_engine import strategy_library as lib
from data_engine import storage
from paper_trading import insights, telegram_bot, challenge_mode

# A strategy needs at least this many CONSECUTIVE losses right now before
# it's called out by name -- a 1-2 loss blip is normal noise, not a
# pattern worth a human's attention in a daily summary.
MIN_LOSING_STREAK_TO_FLAG = 3

# Batch Batch 7 Task 3's own "HIGH CONFIDENCE SIGNAL" marker text
# (paper_trading.telegram_bot._LABELS[...]["high_confidence"]) -- both
# language variants use the identical marker, so a plain substring check
# on the already-logged message_text reliably tells High tier from Low
# tier without needing a new schema column.
_HIGH_CONFIDENCE_MARKER = "HIGH CONFIDENCE SIGNAL"


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _today_start_iso(now):
    return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def _month_start_iso(now):
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


def generate_daily_report(now=None):
    """Pure computation, no sending -- returns {"report_text": <Roman
    Urdu string>, plus every individual figure the text is built from},
    so the Telegram message and any dashboard display of the same report
    always agree, and so this can be unit-tested without touching
    Telegram at all."""
    now = now or datetime.now(timezone.utc)
    today_start_iso = _today_start_iso(now)
    month_start_iso = _month_start_iso(now)

    sent_texts = storage.list_telegram_send_texts_since(today_start_iso)
    high_count = sum(1 for t in sent_texts if _HIGH_CONFIDENCE_MARKER in t)
    low_count = len(sent_texts) - high_count

    today_summary = storage.get_paper_period_summary(today_start_iso, None)
    month_summary = storage.get_paper_period_summary(month_start_iso, None)

    strategy_stats_today = storage.list_paper_strategy_stats(today_start_iso, None)
    best_today = max(strategy_stats_today, key=lambda s: s["total_pnl"], default=None) if strategy_stats_today else None

    streaks = insights.all_streaks()
    # Names come from paper_positions' own recorded strategy_name (the
    # real name a trade was placed under) first -- the same source
    # list_paper_strategy_stats() already trusts -- with the CURRENT
    # strategy library name overlaid where that strategy still exists
    # (picks up a rename), exactly like paper_trading.py's own
    # _compute_analytics() already does for the Strategy Comparison table.
    names = {s["strategy_id"]: s["strategy_name"] for s in storage.list_paper_strategy_stats()}
    names.update({m["id"]: m["name"] for m in lib.list_all() if m["id"] in names})
    losing_streaks = sorted(
        (
            {"strategy_id": sid, "strategy_name": names.get(sid, sid), "count": s["count"]}
            for sid, s in streaks.items() if s["type"] == "loss" and s["count"] >= MIN_LOSING_STREAK_TO_FLAG
        ),
        key=lambda s: s["count"], reverse=True,
    )

    lines = [f"Roz Ki Report -- {now.strftime('%Y-%m-%d')}", ""]

    if sent_texts:
        lines.append(
            f"Aaj {len(sent_texts)} signal(s) Telegram par bheje gaye -- "
            f"{high_count} High Confidence, {low_count} regular."
        )
    else:
        lines.append("Aaj tak koi signal Telegram par nahi bheja gaya.")

    if today_summary["closed_trades"]:
        lines.append(
            f"Aaj {today_summary['closed_trades']} trade(s) band huay, {today_summary['win_count']} jeete -- "
            f"aaj ka PnL: ${today_summary['total_pnl']:.2f}."
        )
    else:
        lines.append("Aaj koi trade band nahi hua.")

    if month_summary["closed_trades"]:
        lines.append(
            f"Is mahine ab tak ka PnL: ${month_summary['total_pnl']:.2f} "
            f"({month_summary['closed_trades']} trades band hue)."
        )
    else:
        lines.append("Is mahine ab tak koi trade band nahi hua.")

    if best_today and best_today["total_pnl"] > 0:
        lines.append(f"Aaj ki sabse achi strategy: {best_today['strategy_name']} (${best_today['total_pnl']:.2f}).")
    elif strategy_stats_today:
        lines.append("Aaj koi strategy profit mein nahi hai.")
    else:
        lines.append("Aaj kisi strategy ka koi trade band nahi hua.")

    if losing_streaks:
        lines.append("Losing streak par strategies:")
        for s in losing_streaks[:5]:
            lines.append(f"  - {s['strategy_name']}: {s['count']} trades laga taar haar rahi hai.")
    else:
        lines.append("Is waqt koi strategy losing streak par nahi hai.")

    # Batch 9, Task 4: only ever added when the CEO has explicitly opted
    # this specific challenge into the daily report -- reuses
    # challenge_mode.compute_progress()'s already-computed numbers
    # verbatim, never a second calculation.
    challenge_progress = challenge_mode.compute_progress(now_iso=now.isoformat())
    if challenge_progress and challenge_progress.get("telegram_report_enabled"):
        lines.append("")
        lines.append(
            f"Challenge: ${challenge_progress['start_amount']:.2f} -> "
            f"${challenge_progress['target_amount']:.2f} mein {challenge_progress['days']} din."
        )
        lines.append(
            f"Abhi tak: ${challenge_progress['current_amount']:.2f} "
            f"({challenge_progress['progress_pct']:.1f}% raasta tay), "
            f"{challenge_progress['remaining_days']:.1f} din baaki, "
            f"{'pace se aage' if challenge_progress['ahead_of_pace'] else 'pace se peeche'} hain."
        )
        lines.append(challenge_progress["honest_note"])

    report_text = "\n".join(lines)
    return {
        "report_text": report_text,
        "signals_sent_today": len(sent_texts), "high_confidence_count": high_count, "low_tier_count": low_count,
        "today_closed_trades": today_summary["closed_trades"], "today_wins": today_summary["win_count"],
        "today_pnl": today_summary["total_pnl"],
        "month_to_date_pnl": month_summary["total_pnl"],
        "month_to_date_closed_trades": month_summary["closed_trades"],
        "best_strategy_today": best_today,
        "losing_streaks": losing_streaks,
        "challenge_progress": challenge_progress,
    }


def maybe_send_daily_report(now=None):
    """Called periodically by the scheduler thread. Sends nothing if:
    the Telegram master switch is off, or a report already went out
    today (date comparison against the last successful daily_report
    send, so this is safe to call as often as convenient -- never sends
    twice in the same calendar day)."""
    if not telegram_bot._master_enabled():
        return None
    now = now or datetime.now(timezone.utc)
    last_sent_iso = storage.get_last_daily_report_sent_at()
    if last_sent_iso:
        last_dt = datetime.fromisoformat(last_sent_iso)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        if last_dt.date() == now.date():
            return None

    result = generate_daily_report(now)
    ok, err = telegram_bot._raw_send(result["report_text"])
    storage.log_telegram_message(
        None, None, None, "daily_report", result["report_text"], ok, err, now.isoformat(),
    )
    return {"ok": ok, "error": err, **result}


def start_daily_report_scheduler_thread():
    """Runs once at server startup; checks periodically whether today's
    report has gone out yet -- same shape as
    paper_trading.weekly_report.start_weekly_report_scheduler_thread."""
    import threading
    import time
    from data_engine.logging_setup import log

    def _loop():
        while True:
            try:
                result = maybe_send_daily_report()
                if result:
                    log(f"[daily-report] sent (ok={result['ok']})")
            except Exception as e:
                log(f"[daily-report] failed: {e!r}")
            time.sleep(3600)  # hourly check; the same-calendar-day gate above prevents over-sending
    threading.Thread(target=_loop, daemon=True).start()
