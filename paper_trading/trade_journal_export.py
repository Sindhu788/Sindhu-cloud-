"""Trade Journal Export to PDF (Grand Feature Expansion, Phase 4 Feature
23): a trade-by-trade record of real paper-trading history. Distinct from
the only other paper-trading export that exists (an Excel strategy-vs-
strategy COMPARISON aggregate, not a per-trade journal) and from
backtest_engine/export.py's export_pdf (backtest report only, never
paper-trading data). Reuses reportlab exactly like that existing PDF
export -- reportlab is already an installed dependency, so this adds
nothing new to the project's footprint."""

import os
from datetime import datetime, timezone

from data_engine import storage
from data_engine.paths import REPORTS_DIR

_EXPORT_DIR = os.path.join(REPORTS_DIR, "trade_journal_exports")


def export_trade_journal_pdf(strategy_id=None, limit=200):
    """One PDF, one row per closed trade, newest first (same ordering
    storage.list_closed_paper_positions already uses everywhere else).
    strategy_id=None exports across every strategy's closed trades."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm

    os.makedirs(_EXPORT_DIR, exist_ok=True)
    trades = storage.list_closed_paper_positions(limit=limit, strategy_id=strategy_id)
    generated_at = datetime.now(timezone.utc).isoformat()
    file_label = strategy_id or "all_strategies"
    out_path = os.path.join(
        _EXPORT_DIR, f"trade_journal_{file_label}_{int(datetime.now(timezone.utc).timestamp())}.pdf"
    )

    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(out_path, pagesize=landscape(A4))
    strategy_label = trades[0]["strategy_name"] if trades else (strategy_id or "All Strategies")
    story = [
        Paragraph("SINDHU Trade Journal", styles["Title"]),
        Paragraph(f"Strategy: {strategy_label}", styles["Normal"]),
        Paragraph(f"Trades: {len(trades)}", styles["Normal"]),
        Paragraph(f"Generated: {generated_at}", styles["Normal"]),
        Spacer(1, 0.5 * cm),
    ]

    headers = ["Closed At", "Symbol", "Dir", "Entry", "Exit", "PnL", "PnL %", "R", "Reason", "Note"]
    rows = [headers]
    for t in trades:
        rows.append([
            str(t.get("closed_at") or "")[:19],
            t.get("symbol") or "-",
            t.get("direction") or "-",
            f"{t['entry_price']:.4f}" if t.get("entry_price") is not None else "-",
            f"{t['exit_price']:.4f}" if t.get("exit_price") is not None else "-",
            f"{t['pnl']:.2f}" if t.get("pnl") is not None else "-",
            f"{t['pnl_pct']:.2f}%" if t.get("pnl_pct") is not None else "-",
            f"{t['rr']:.2f}" if t.get("rr") is not None else "-",
            (t.get("exit_reason") or "-")[:30],
            (t.get("user_note") or "-")[:40],
        ])

    if len(trades) == 0:
        story.append(Paragraph("No closed trades to show for this selection.", styles["Normal"]))
    else:
        table = Table(rows, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
        ]))
        story.append(table)

    doc.build(story)
    return out_path
