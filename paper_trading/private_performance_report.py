"""Master 15-Item task, Item 10: Private Telegram Report Delivery (Weekly +
Monthly), in Hinglish, as a PDF, delivered ONLY to the CEO's own private
personal_chat_id (paper_trading.telegram_bot.send_private_document) --
never to the public/shared Telegram channel.

Distinct from the existing paper_trading.weekly_report/monthly_report
modules (which generate a plain-text, PUBLIC-channel narrative summary of
which strategies did well/poorly -- a different purpose, kept unchanged).
This module computes exactly the metric set asked for (Win Rate, Profit
Factor, Net Profit, Max Drawdown, Average Win/Loss, Total Trades) plus an
Original-vs-Evolution-Generation comparison table, reusing already-
computed data wherever it exists rather than inventing a second source of
truth:
  - The 6 headline metrics come straight from paper_positions (real,
    closed, live Paper Trading trades only -- BOT-generated Evolution
    candidates are never paper-traded, see evolution_engine/rollback.py's
    own docstring, so this section is entirely "Original"/manually-
    imported-or-self-learning strategies' real live performance).
  - The Original-vs-Evolution-Generation table reuses evolution_engine's
    own ALREADY-COMPUTED before/after backtest comparison
    (data_engine.storage.list_evolution_comparisons_between --
    evolution_engine/rollback.py's 4-metric comparison every lineage that
    crossed its 100-trade evolution gate already has stored) -- nothing
    new is computed for this table, only formatted.
"""
import os
from datetime import datetime, timedelta, timezone

from data_engine import config as base_config, storage
from data_engine.paths import REPORTS_DIR
from paper_trading import telegram_bot

_EXPORT_DIR = os.path.join(REPORTS_DIR, "private_performance_reports")

WEEKLY_INTERVAL_DAYS = 7
MONTHLY_INTERVAL_DAYS = 30
_STATE_FILE = "private_performance_report_state.json"
_STATE_DEFAULTS = {"last_weekly_sent_at": None, "last_monthly_sent_at": None}


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def compute_period_performance_metrics(period_start_iso, period_end_iso):
    """Account-wide (every strategy combined), closed trades only, in
    [period_start_iso, period_end_iso). Same raw-SQL aggregation style
    already used elsewhere in this project (e.g. weekly_report.py's own
    daily-PnL query) -- Profit Factor and Average Win/Loss aren't computed
    anywhere else at the account level, so this is genuinely new
    aggregation, but over data (paper_positions) every other feature here
    already reads."""
    with storage.get_conn() as conn:
        rows = conn.execute(
            "SELECT pnl FROM paper_positions WHERE status='closed' AND pnl IS NOT NULL "
            "AND closed_at >= ? AND closed_at < ?",
            (period_start_iso, period_end_iso),
        ).fetchall()
    pnls = [r[0] for r in rows]
    total_trades = len(pnls)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    net_profit = sum(pnls)
    win_rate = round(len(wins) / total_trades * 100, 2) if total_trades else 0.0
    profit_factor = round(gross_profit / gross_loss, 3) if gross_loss else None
    avg_win = round(gross_profit / len(wins), 2) if wins else 0.0
    avg_loss = round(-gross_loss / len(losses), 2) if losses else 0.0

    # Max Drawdown: same peak-to-trough-of-cumulative-equity definition as
    # paper_trading.insights.compute_risk_metrics, applied here to just
    # this period's own trade sequence (oldest-to-newest) rather than the
    # whole account history, since the report is period-scoped.
    with storage.get_conn() as conn:
        ordered = conn.execute(
            "SELECT pnl FROM paper_positions WHERE status='closed' AND pnl IS NOT NULL "
            "AND closed_at >= ? AND closed_at < ? ORDER BY closed_at ASC",
            (period_start_iso, period_end_iso),
        ).fetchall()
    running = 0.0
    peak = 0.0
    max_dd = 0.0
    for (p,) in ordered:
        running += p
        peak = max(peak, running)
        max_dd = max(max_dd, peak - running)
    max_drawdown_pct = round(max_dd, 2)  # in dollars, same as net_profit's own unit -- no fixed "initial balance" assumed here

    return {
        "total_trades": total_trades,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "net_profit": round(net_profit, 2),
        "max_drawdown": max_drawdown_pct,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
    }


def original_vs_evolution_comparison_rows(period_start_iso, period_end_iso):
    """Every evolution_comparisons row FINALIZED (has a real 'after') in
    the period -- 'Original' = the parent generation's own backtest
    numbers ('before'), 'Evolution-Generation' = the child's ('after')."""
    comparisons = storage.list_evolution_comparisons_between(period_start_iso, period_end_iso)
    rows = []
    for c in comparisons:
        if not c.get("after"):
            continue
        rows.append({
            "base_id": c["base_id"],
            "verdict": c["verdict"],
            "rolled_back": c["rolled_back"],
            "original": c["before"],
            "evolution_generation": c["after"],
        })
    return rows


def generate_report_pdf(period_label, period_start_iso, period_end_iso):
    """period_label: e.g. "Weekly" or "Monthly", used only in the title/
    filename. Returns the PDF file's path."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm

    os.makedirs(_EXPORT_DIR, exist_ok=True)
    metrics = compute_period_performance_metrics(period_start_iso, period_end_iso)
    comparison_rows = original_vs_evolution_comparison_rows(period_start_iso, period_end_iso)
    generated_at = _now_iso()

    out_path = os.path.join(
        _EXPORT_DIR, f"{period_label.lower()}_performance_{int(datetime.now(timezone.utc).timestamp())}.pdf"
    )

    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(out_path, pagesize=A4)
    story = [
        Paragraph(f"SINDHU {period_label} Performance Report", styles["Title"]),
        Paragraph(f"Period: {period_start_iso[:10]} se {period_end_iso[:10]} tak", styles["Normal"]),
        Paragraph(f"Banaya gaya: {generated_at[:19]} UTC", styles["Normal"]),
        Spacer(1, 0.6 * cm),
        Paragraph("Real Paper Trading Performance (is period ka)", styles["Heading2"]),
    ]

    metric_rows = [
        ["Metric", "Value"],
        ["Total Trades", str(metrics["total_trades"])],
        ["Win Rate", f"{metrics['win_rate']}%"],
        ["Profit Factor", f"{metrics['profit_factor']}" if metrics["profit_factor"] is not None else "N/A (koi loss nahi hua)"],
        ["Net Profit", f"${metrics['net_profit']:.2f}"],
        ["Max Drawdown", f"${metrics['max_drawdown']:.2f}"],
        ["Average Win", f"${metrics['avg_win']:.2f}"],
        ["Average Loss", f"${metrics['avg_loss']:.2f}"],
    ]
    metric_table = Table(metric_rows, colWidths=[8 * cm, 6 * cm])
    metric_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
    ]))
    story.append(metric_table)
    story.append(Spacer(1, 0.6 * cm))

    story.append(Paragraph("Original vs Evolution-Generation Comparison", styles["Heading2"]))
    if not comparison_rows:
        story.append(Paragraph(
            "Is period mein koi lineage 100-trade evolution gate cross nahi hui -- abhi comparison ke liye koi data nahi hai.",
            styles["Normal"],
        ))
    else:
        cmp_header = ["Strategy Lineage", "Version", "Win Rate", "Profit Factor", "Max DD %", "Kept?"]
        cmp_rows = [cmp_header]
        for r in comparison_rows:
            o, e = r["original"], r["evolution_generation"]
            kept = "Rolled back" if r["rolled_back"] else "Kept"
            cmp_rows.append([r["base_id"], "Original", f"{o.get('win_rate', 0):.1f}%", f"{o.get('avg_profit_factor', 0):.2f}", f"{o.get('max_drawdown_pct', 0):.1f}%", ""])
            cmp_rows.append(["", "Evolution-Gen", f"{e.get('win_rate', 0):.1f}%", f"{e.get('avg_profit_factor', 0):.2f}", f"{e.get('max_drawdown_pct', 0):.1f}%", kept])
        cmp_table = Table(cmp_rows, repeatRows=1)
        cmp_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
        ]))
        story.append(cmp_table)

    story.append(Spacer(1, 0.6 * cm))
    story.append(Paragraph(
        "Yeh report sirf aap (CEO) ko private message mein bheji gayi hai -- public Telegram channel mein nahi. "
        "Experimental system, trading advice nahi hai.",
        styles["Normal"],
    ))

    doc.build(story)
    return out_path


def send_report(period_label, period_start_iso, period_end_iso):
    """Generates the PDF, then delivers it via telegram_bot.
    send_private_document. Returns {"ok": bool, "error": str|None,
    "pdf_path": str}. The PDF is always generated and kept on disk even
    if the Telegram send fails (same "never lose the report just because
    delivery failed" principle as every other report in this project)."""
    pdf_path = generate_report_pdf(period_label, period_start_iso, period_end_iso)
    result = telegram_bot.send_private_document(
        pdf_path, caption=f"SINDHU {period_label} Performance Report ({period_start_iso[:10]} se {period_end_iso[:10]} tak)"
    )
    result["pdf_path"] = pdf_path
    return result


def _load_state():
    return base_config.load_or_seed(_STATE_FILE, _STATE_DEFAULTS)


def _save_state(state):
    base_config.save_config(_STATE_FILE, state)


def maybe_send_weekly_report():
    """Same gate shape as paper_trading.weekly_report.maybe_generate_
    weekly_report -- only sends if 7+ days have passed (or never sent).
    Silently no-ops (returns None, does NOT raise) if personal_chat_id
    isn't configured yet, so the scheduler thread never spams the logs
    with the same "not configured" error every check forever."""
    settings = telegram_bot.load_settings()
    if not settings.get("personal_chat_id"):
        return None
    state = _load_state()
    now = datetime.now(timezone.utc)
    last = state.get("last_weekly_sent_at")
    if last and (now - datetime.fromisoformat(last)) < timedelta(days=WEEKLY_INTERVAL_DAYS):
        return None
    period_start = (now - timedelta(days=WEEKLY_INTERVAL_DAYS)).isoformat()
    result = send_report("Weekly", period_start, now.isoformat())
    state["last_weekly_sent_at"] = now.isoformat()
    _save_state(state)
    return result


def maybe_send_monthly_report():
    settings = telegram_bot.load_settings()
    if not settings.get("personal_chat_id"):
        return None
    state = _load_state()
    now = datetime.now(timezone.utc)
    last = state.get("last_monthly_sent_at")
    if last and (now - datetime.fromisoformat(last)) < timedelta(days=MONTHLY_INTERVAL_DAYS):
        return None
    period_start = (now - timedelta(days=MONTHLY_INTERVAL_DAYS)).isoformat()
    result = send_report("Monthly", period_start, now.isoformat())
    state["last_monthly_sent_at"] = now.isoformat()
    _save_state(state)
    return result


def start_private_report_scheduler_thread():
    """LOCAL APP ONLY -- call from sindhu_web/server.py's lifespan, same
    as paper_trading.weekly_report/monthly_report's own schedulers,
    NEVER from cloud_runtime/app.py: reportlab (PDF generation) is
    deliberately not in requirements-cloud.txt (the lightweight cloud
    runner's own dependency list), since PDF/report generation is one of
    the desktop-only features that file's own docstring already excludes."""
    import threading
    import time
    from data_engine.logging_setup import log

    def _loop():
        while True:
            try:
                if maybe_send_weekly_report():
                    log("[private-report] sent a new private Weekly Performance Report")
                if maybe_send_monthly_report():
                    log("[private-report] sent a new private Monthly Performance Report")
            except Exception as e:
                log(f"[private-report] generation/send failed: {e!r}")
            time.sleep(6 * 3600)  # check every 6 hours, same convention as weekly_report.py

    threading.Thread(target=_loop, daemon=True).start()
