"""One-click export of a batch's results to CSV, Excel, or PDF. Reads
whatever generate_report() already computed/saved -- these functions never
recompute metrics, they just reformat report.json + the trades table."""

import json
import os

import pandas as pd

from data_engine import storage
from data_engine.paths import REPORTS_DIR


def _load_summary(batch_id):
    path = os.path.join(REPORTS_DIR, batch_id, "report.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _export_dir(batch_id):
    out_dir = os.path.join(REPORTS_DIR, batch_id, "exports")
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def export_csv(batch_id):
    """Writes results_summary.csv and trades.csv. Returns their paths."""
    summary = _load_summary(batch_id)
    trades = storage.get_trades(batch_id)
    out_dir = _export_dir(batch_id)

    results_rows = [
        {"symbol": r["symbol"], "timeframe": r["timeframe"], "status": r["status"], **(r["metrics"] or {})}
        for r in summary["results"]
    ]
    results_path = os.path.join(out_dir, "results_summary.csv")
    pd.DataFrame(results_rows).to_csv(results_path, index=False)

    trades_path = os.path.join(out_dir, "trades.csv")
    pd.DataFrame(trades).to_csv(trades_path, index=False)

    return {"results_summary": results_path, "trades": trades_path}


def export_excel(batch_id):
    """One .xlsx with a sheet per view: Summary, Coin Ranking, Timeframe
    Ranking, Session Analysis, Trades. Returns the file path."""
    summary = _load_summary(batch_id)
    trades = storage.get_trades(batch_id)
    out_path = os.path.join(_export_dir(batch_id), "report.xlsx")

    overview = {k: v for k, v in summary.items() if k not in
                ("results", "coin_ranking", "timeframe_ranking", "session_analysis", "settings")}

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        pd.DataFrame([overview]).T.rename(columns={0: "value"}).to_excel(writer, sheet_name="Summary")
        pd.DataFrame(summary["coin_ranking"]).to_excel(writer, sheet_name="Coin Ranking", index=False)
        pd.DataFrame(summary["timeframe_ranking"]).to_excel(writer, sheet_name="Timeframe Ranking", index=False)
        pd.DataFrame(summary["session_analysis"]).to_excel(writer, sheet_name="Session Analysis", index=False)
        pd.DataFrame(trades).to_excel(writer, sheet_name="Trades", index=False)

    return out_path


def export_pdf(batch_id):
    """A readable one-page-plus PDF summary: overview, coin ranking,
    timeframe ranking, session analysis. Returns the file path."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm

    summary = _load_summary(batch_id)
    out_path = os.path.join(_export_dir(batch_id), "report.pdf")
    styles = getSampleStyleSheet()

    doc = SimpleDocTemplate(out_path, pagesize=A4)
    story = [
        Paragraph("SINDHU Backtest Report", styles["Title"]),
        Paragraph(f"Strategy: {summary['strategy']}", styles["Normal"]),
        Paragraph(f"Exchange: {summary['exchange']}", styles["Normal"]),
        Paragraph(f"Generated: {summary['generated_at']}", styles["Normal"]),
        Spacer(1, 0.5 * cm),
    ]

    def _table(title, headers, rows):
        elements = [Paragraph(title, styles["Heading2"])]
        data = [headers] + rows
        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 0.5 * cm))
        return elements

    overview_rows = [
        ["Total Trades", summary["total_trades"]], ["Wins", summary["wins"]], ["Losses", summary["losses"]],
        ["Win Rate %", summary["win_rate"]], ["Avg Profit %", summary["avg_profit_pct"]],
        ["Max Drawdown %", summary["max_drawdown_pct"]], ["Profit Factor", summary["avg_profit_factor"]],
        ["Risk Reward", summary["avg_risk_reward"]],
        ["Best Coin", summary["best_coin"]], ["Worst Coin", summary["worst_coin"]],
        ["Best Timeframe", summary["best_timeframe"]], ["Worst Timeframe", summary["worst_timeframe"]],
        ["Best Session", summary["best_session"]], ["Worst Session", summary["worst_session"]],
    ]
    story += _table("Overview", ["Metric", "Value"], [[str(a), str(b)] for a, b in overview_rows])

    coin_rows = [[r["symbol"], f"{r['avg_profit_pct']}%", f"{r['win_rate']}%", r["total_trades"], f"{r['max_drawdown_pct']}%"]
                 for r in summary["coin_ranking"]]
    story += _table("Coin Ranking", ["Coin", "Profit", "Win Rate", "Trades", "Drawdown"], coin_rows)

    tf_rows = [[r["timeframe"], f"{r['avg_profit_pct']}%", f"{r['win_rate']}%", r["total_trades"], f"{r['max_drawdown_pct']}%"]
               for r in summary["timeframe_ranking"]]
    story += _table("Timeframe Ranking", ["Timeframe", "Profit", "Win Rate", "Trades", "Drawdown"], tf_rows)

    session_rows = [[r["session"], r["trades"], f"{r['win_rate']}%", r["total_pnl"]] for r in summary["session_analysis"]]
    story += _table("Session Analysis", ["Session", "Trades", "Win Rate", "Total PnL"], session_rows)

    doc.build(story)
    return out_path
