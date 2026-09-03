"""Monthly Auto-Report (Grand Feature Expansion, Phase 3 Feature 13): the
exact same shape as paper_trading/weekly_report.py (deliberately -- this
codebase already established that report shape and its own tests/CEO
familiarity with it), just a 30-day interval instead of 7 and its own
storage table/generation gate so the two never interfere with each other.
Reuses weekly_report's own sparkline helper rather than duplicating it.
"""

from datetime import datetime, timezone, timedelta

from data_engine import storage, feature_toggles
from backtest_engine import strategy_library as lib
from paper_trading import insights, telegram_bot
from paper_trading.weekly_report import _daily_pnl_sparkline

REPORT_INTERVAL_DAYS = 30


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def generate_monthly_report():
    now = datetime.now(timezone.utc)
    period_start = (now - timedelta(days=REPORT_INTERVAL_DAYS)).isoformat()
    period_end = now.isoformat()
    since = insights.fresh_session_start()

    strategies = []
    for meta in lib.list_all():
        sid = meta["id"]
        with storage.get_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*), SUM(CASE WHEN status='closed' THEN 1 ELSE 0 END), "
                "SUM(CASE WHEN status='closed' AND pnl>0 THEN 1 ELSE 0 END), "
                "SUM(CASE WHEN status='closed' THEN pnl ELSE 0 END) "
                "FROM paper_positions WHERE strategy_id=? AND created_at >= ?", (sid, since)
            ).fetchone()
        total, closed, wins, pnl = row
        closed = closed or 0
        if closed == 0:
            continue
        win_rate = round((wins or 0) / closed * 100, 1)
        pnl = round(pnl or 0, 2)
        paused, pause_reason, _ = storage.is_strategy_paused(sid)
        strategies.append({
            "id": sid, "name": meta["name"], "closed_trades": closed,
            "win_rate": win_rate, "pnl": pnl, "paused": paused, "pause_reason": pause_reason,
        })

    strategies.sort(key=lambda s: s["pnl"], reverse=True)
    doing_well = [s for s in strategies if s["pnl"] > 0 and s["win_rate"] >= 50]
    doing_poorly = [s for s in strategies if s["pnl"] < 0 or s["win_rate"] < 30]
    paused_strategies = [s for s in strategies if s["paused"]]

    auto_lessons = storage.list_paper_auto_lessons(active_only=True)
    avoid_rules = storage.list_paper_auto_avoid_rules(active_only=True)

    retire_candidates = [s for s in doing_poorly if s["closed_trades"] >= 10 and s["paused"]]
    watch_candidates = [s for s in doing_well if s["closed_trades"] < 20]

    lines = [
        f"Monthly Report -- {now.strftime('%Y-%m-%d')}",
        "",
        f"This covers {len(strategies)} strategies with at least one completed trade in the last {REPORT_INTERVAL_DAYS} days.",
        "",
        _daily_pnl_sparkline(period_start, period_end),
        "",
    ]

    if doing_well:
        lines.append("Strategies that did WELL this month:")
        for s in doing_well[:5]:
            lines.append(f"  - {s['name']}: {s['closed_trades']} trades finished, won {s['win_rate']}% of them, made ${s['pnl']:.2f} overall.")
        lines.append("")

    if doing_poorly:
        lines.append("Strategies that did POORLY this month:")
        for s in doing_poorly[:5]:
            lines.append(f"  - {s['name']}: {s['closed_trades']} trades finished, only won {s['win_rate']}% of them, lost ${abs(s['pnl']):.2f} overall." if s["pnl"] < 0
                         else f"  - {s['name']}: {s['closed_trades']} trades finished, only won {s['win_rate']}% of them.")
        lines.append("")

    if paused_strategies:
        lines.append("Strategies automatically PAUSED by the safety system this month (no new trades, existing ones still watched normally):")
        for s in paused_strategies:
            lines.append(f"  - {s['name']}: {s['pause_reason']}")
        lines.append("")

    if auto_lessons:
        lines.append(f"The system automatically learned {len(auto_lessons)} lesson(s) from real trading patterns:")
        for l in auto_lessons[:5]:
            lines.append(f"  - {l['explanation']}")
        lines.append("")

    if avoid_rules:
        lines.append(f"{len(avoid_rules)} specific losing pattern(s) are currently being avoided:")
        for r in avoid_rules[:5]:
            lines.append(f"  - {r['reason']}")
        lines.append("")

    lines.append("Recommendations:")
    if retire_candidates:
        for s in retire_candidates:
            lines.append(f"  - Consider retiring \"{s['name']}\" -- it has enough real trades ({s['closed_trades']}) showing a consistent problem and is currently paused for safety.")
    if watch_candidates:
        for s in watch_candidates:
            lines.append(f"  - Keep watching \"{s['name']}\" -- it's doing well so far, but only has {s['closed_trades']} trades, too early to be fully confident.")
    if not retire_candidates and not watch_candidates:
        lines.append("  - Nothing urgent to act on this month -- keep monitoring as usual.")

    report_text = "\n".join(lines)
    report_data = {
        "strategies": strategies, "doing_well": [s["id"] for s in doing_well],
        "doing_poorly": [s["id"] for s in doing_poorly], "paused": [s["id"] for s in paused_strategies],
        "auto_lessons_count": len(auto_lessons), "avoid_rules_count": len(avoid_rules),
        "retire_candidates": [s["id"] for s in retire_candidates],
        "watch_candidates": [s["id"] for s in watch_candidates],
    }

    import json
    storage.save_monthly_report(period_start, period_end, json.dumps(report_data), report_text, _now_iso())
    return {"report_text": report_text, "report_data": report_data}


def maybe_generate_monthly_report():
    """Same contract as weekly_report.maybe_generate_weekly_report(): only
    generates (and Telegram-sends) a new report if REPORT_INTERVAL_DAYS
    have passed since the last one, using its own paper_monthly_reports
    table so this gate never interferes with the weekly one."""
    if not feature_toggles.is_enabled("monthly_report_enabled"):
        return None
    last = storage.get_latest_monthly_report()
    if last:
        last_dt = datetime.fromisoformat(last)
        if datetime.now(timezone.utc) - last_dt < timedelta(days=REPORT_INTERVAL_DAYS):
            return None
    result = generate_monthly_report()
    if telegram_bot._master_enabled():
        ok, err = telegram_bot._raw_send(result["report_text"])
        storage.log_telegram_message(
            None, None, None, "monthly_report", result["report_text"], ok, err, _now_iso(),
        )
        result["telegram_sent"] = ok
        result["telegram_error"] = err
    return result


def start_monthly_report_scheduler_thread():
    """Runs once at server startup; checks daily whether a new report is
    due -- same shape as paper_trading.weekly_report's own scheduler
    thread, just a longer check interval since a 30-day gate needs far
    less frequent polling than a 7-day one."""
    import threading
    import time
    from data_engine.logging_setup import log

    def _loop():
        while True:
            try:
                result = maybe_generate_monthly_report()
                if result:
                    log("[monthly-report] generated a new monthly report")
            except Exception as e:
                log(f"[monthly-report] generation failed: {e!r}")
            time.sleep(24 * 3600)  # check once a day; the 30-day gate above prevents over-generating

    threading.Thread(target=_loop, daemon=True).start()
