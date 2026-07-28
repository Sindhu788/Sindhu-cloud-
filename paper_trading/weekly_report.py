"""Weekly Auto-Report (Dashboard Consolidation Group, item 7): a scheduled,
plain-language summary generated every 7 days from data every other
feature in this project already computes (insights, drawdown_guard,
lesson_auto_apply, strategy_library) -- nothing new is calculated here,
only assembled into simple sentences and stored permanently so it can be
reviewed later. Written for someone with no trading background: no jargon
like "Sharpe Ratio" without explanation, no raw numbers without context.
"""

from datetime import datetime, timezone, timedelta

from data_engine import storage, feature_toggles
from backtest_engine import strategy_library as lib
from paper_trading import insights

REPORT_INTERVAL_DAYS = 7


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def generate_weekly_report():
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
            continue  # degrade gracefully -- nothing to report on a strategy with zero closed trades
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

    # Simple recommendation logic (plain thresholds, no hidden model):
    # a strategy with a real sample size (10+ trades) doing badly AND
    # currently paused is a genuine "consider retiring" candidate; one
    # doing well but with too few trades yet is a "keep watching" one.
    retire_candidates = [s for s in doing_poorly if s["closed_trades"] >= 10 and s["paused"]]
    watch_candidates = [s for s in doing_well if s["closed_trades"] < 20]

    lines = [
        f"Weekly Report -- {now.strftime('%Y-%m-%d')}",
        "",
        f"This covers {len(strategies)} strategies with at least one completed trade in the last {REPORT_INTERVAL_DAYS} days.",
        "",
    ]

    if doing_well:
        lines.append("Strategies that did WELL this week:")
        for s in doing_well[:5]:
            lines.append(f"  - {s['name']}: {s['closed_trades']} trades finished, won {s['win_rate']}% of them, made ${s['pnl']:.2f} overall.")
        lines.append("")

    if doing_poorly:
        lines.append("Strategies that did POORLY this week:")
        for s in doing_poorly[:5]:
            lines.append(f"  - {s['name']}: {s['closed_trades']} trades finished, only won {s['win_rate']}% of them, lost ${abs(s['pnl']):.2f} overall." if s["pnl"] < 0
                         else f"  - {s['name']}: {s['closed_trades']} trades finished, only won {s['win_rate']}% of them.")
        lines.append("")

    if paused_strategies:
        lines.append("Strategies automatically PAUSED by the safety system this week (no new trades, existing ones still watched normally):")
        for s in paused_strategies:
            lines.append(f"  - {s['name']}: {s['pause_reason']}")
        lines.append("")

    if auto_lessons:
        lines.append(f"The system automatically learned {len(auto_lessons)} lesson(s) from real trading patterns this week:")
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
        lines.append("  - Nothing urgent to act on this week -- keep monitoring as usual.")

    report_text = "\n".join(lines)
    report_data = {
        "strategies": strategies, "doing_well": [s["id"] for s in doing_well],
        "doing_poorly": [s["id"] for s in doing_poorly], "paused": [s["id"] for s in paused_strategies],
        "auto_lessons_count": len(auto_lessons), "avoid_rules_count": len(avoid_rules),
        "retire_candidates": [s["id"] for s in retire_candidates],
        "watch_candidates": [s["id"] for s in watch_candidates],
    }

    import json
    storage.save_weekly_report(period_start, period_end, json.dumps(report_data), report_text, _now_iso())
    return {"report_text": report_text, "report_data": report_data}


def maybe_generate_weekly_report():
    """Called periodically by the scheduler thread -- only actually
    generates a new report if 7+ days have passed since the last one (or
    none exists yet). Safe to call as often as convenient."""
    if not feature_toggles.is_enabled("weekly_report_enabled"):
        return None
    last = storage.get_latest_weekly_report()
    if last:
        last_dt = datetime.fromisoformat(last)
        if datetime.now(timezone.utc) - last_dt < timedelta(days=REPORT_INTERVAL_DAYS):
            return None
    return generate_weekly_report()


def start_weekly_report_scheduler_thread():
    """Runs once at server startup; checks every few hours whether a new
    report is due -- same shape as sindhu_web.api.backup.start_auto_backup_thread."""
    import threading
    import time
    from data_engine.logging_setup import log

    def _loop():
        while True:
            try:
                result = maybe_generate_weekly_report()
                if result:
                    log("[weekly-report] generated a new weekly report")
            except Exception as e:
                log(f"[weekly-report] generation failed: {e!r}")
            time.sleep(6 * 3600)  # check every 6 hours; the 7-day gate above prevents over-generating

    threading.Thread(target=_loop, daemon=True).start()
