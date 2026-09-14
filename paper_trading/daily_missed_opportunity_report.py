"""Grand Master Batch, Phase 6 Item 13: Daily "Missed Opportunity" Report
-- a day-boundary digest of telegram_bot's existing Near-Miss Log (real
signals that qualified for generation but were gated out of High
Confidence, with the real reason), which previously was only a live,
ungrouped cumulative list with no daily cadence (unlike weekly_report.py).
"""

from datetime import datetime, timedelta, timezone

from data_engine import config as base_config, feature_toggles, storage

_CLOUD_KEY = "daily_missed_opportunity_report_state"
_FILE = "daily_missed_opportunity_report.json"
_DEFAULTS = {"last_sent_date": None}


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def generate_report(day=None):
    """day: a date to report on (UTC calendar day) -- defaults to
    yesterday, since a "daily" report naturally summarizes the day that
    just ended, not the still-in-progress current one."""
    day = day or (datetime.now(timezone.utc) - timedelta(days=1)).date()
    start_iso = datetime(day.year, day.month, day.day, tzinfo=timezone.utc).isoformat()
    end_iso = (datetime(day.year, day.month, day.day, tzinfo=timezone.utc) + timedelta(days=1)).isoformat()

    rows = [r for r in storage.list_near_misses(limit=100000, since_iso=start_iso) if r["created_at"] < end_iso]

    by_strategy = {}
    for r in rows:
        name = r.get("strategy_name") or r.get("strategy_id") or "Unknown"
        by_strategy[name] = by_strategy.get(name, 0) + 1
    ranked = sorted(by_strategy.items(), key=lambda kv: kv[1], reverse=True)

    lines = [f"\U0001F4CA Daily Missed Opportunity Report -- {day.isoformat()}", "─" * 18]
    if not rows:
        lines.append("No signals were gated out today -- either nothing qualified for generation, or everything that did also cleared High Confidence.")
    else:
        lines.append(f"{len(rows)} real signal(s) qualified for generation but didn't reach High Confidence:")
        for name, count in ranked[:10]:
            lines.append(f"• {name}: {count}")
        sample_reasons = [r["reason"] for r in rows[:3] if r.get("reason")]
        if sample_reasons:
            lines.append("")
            lines.append("Example reasons:")
            for reason in sample_reasons:
                lines.append(f"• {reason}")

    return {
        "date": day.isoformat(), "total_missed": len(rows),
        "by_strategy": [{"strategy_name": name, "count": count} for name, count in ranked],
        "report_text": "\n".join(lines),
    }


def maybe_send_daily_report():
    """Called periodically by a scheduler thread -- only generates/sends
    once per real calendar day. Off if the CEO has disabled the existing
    weekly_report feature toggle too (same "routine automated report"
    category, no new toggle invented)."""
    if not feature_toggles.is_enabled("weekly_report_enabled"):
        return None
    today = datetime.now(timezone.utc).date().isoformat()
    state = base_config.load_persistent(_CLOUD_KEY, _FILE, _DEFAULTS)
    if state.get("last_sent_date") == today:
        return None

    from paper_trading import telegram_bot
    result = generate_report()
    if telegram_bot._master_enabled():
        ok, err = telegram_bot._raw_send(result["report_text"])
        storage.log_telegram_message(None, None, None, "daily_missed_opportunity_report", result["report_text"], ok, err, _now_iso())
        result["telegram_sent"] = ok
        result["telegram_error"] = err

    state["last_sent_date"] = today
    base_config.save_persistent(_CLOUD_KEY, _FILE, state)
    return result


def start_daily_report_scheduler_thread():
    """Runs once at server startup; checks every hour whether a new report
    is due -- same shape as weekly_report.start_weekly_report_scheduler_thread."""
    import threading
    import time
    from data_engine.logging_setup import log

    def _loop():
        while True:
            try:
                result = maybe_send_daily_report()
                if result:
                    log("[daily-missed-opportunity] sent a new daily report")
            except Exception as e:
                log(f"[daily-missed-opportunity] scheduler error: {e!r}")
            time.sleep(3600)

    threading.Thread(target=_loop, daemon=True).start()
