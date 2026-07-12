import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from data_engine import storage
from backtest_engine.reports import generate_report, quick_batch_summary
from backtest_engine import export

router = APIRouter()


@router.get("/api/reports")
def list_reports():
    return {"batches": storage.list_recent_batches()}


@router.get("/api/backtest-history")
def backtest_history(limit: int = 200):
    """Permanent list of every completed backtest batch for the Backtest
    History page -- unlike live job progress (in-memory, gone on restart),
    this is recomputed from backtest_batches/backtest_results each call, so
    old batches stay visible and browsable indefinitely."""
    batches = storage.list_recent_batches(limit=limit)
    completed = [b for b in batches if b["status"] == "completed"]
    summaries = []
    for b in completed:
        s = quick_batch_summary(b["batch_id"])
        if s:
            s["created_at"] = b["created_at"]
            summaries.append(s)
    return {"batches": summaries}


@router.get("/api/reports/best-worst/strategies")
def best_worst_strategies():
    batches = storage.list_recent_batches(limit=200)
    by_strategy = {}
    for b in batches:
        if b["status"] != "completed":
            continue
        try:
            summary = generate_report(b["batch_id"])
        except Exception:
            continue
        by_strategy.setdefault(b["strategy_name"], []).append(summary["avg_profit_pct"])

    ranked = sorted(
        (
            {"strategy": k, "avg_profit_pct": round(sum(v) / len(v), 2), "batches": len(v)}
            for k, v in by_strategy.items()
        ),
        key=lambda r: r["avg_profit_pct"], reverse=True,
    )
    return {
        "ranking": ranked,
        "best_strategy": ranked[0]["strategy"] if ranked else None,
        "worst_strategy": ranked[-1]["strategy"] if ranked else None,
    }


@router.get("/api/reports/{batch_id}")
def get_report(batch_id: str):
    batch = storage.get_batch(batch_id)
    if not batch:
        raise HTTPException(404, "batch not found")
    return generate_report(batch_id)


@router.get("/api/reports/{batch_id}/condition-reports")
def get_condition_reports(batch_id: str):
    """Per-coin condition-hit diagnostics for every 0-trade result in this
    batch -- for each entry condition, how many bars it was actually true
    (respecting its lookback window), and how many bars every condition
    was true together. Rule-based counting only, computed once when the
    backtest itself ran and stored alongside the batch."""
    if not storage.get_batch(batch_id):
        raise HTTPException(404, "batch not found")
    return {"reports": storage.list_condition_reports(batch_id)}


@router.get("/api/reports/{batch_id}/trades")
def get_batch_trades(batch_id: str):
    """Chronological trade list for the batch -- the frontend builds the
    Equity Curve / Drawdown charts from this (cumulative pnl_pct over
    time), rather than the server pre-computing a chart."""
    if not storage.get_batch(batch_id):
        raise HTTPException(404, "batch not found")
    trades = storage.get_trades(batch_id)
    trades.sort(key=lambda t: t["entry_time"] or 0)
    return {"trades": trades}


@router.get("/api/reports/{batch_id}/export/{fmt}")
def export_report(batch_id: str, fmt: str):
    if not storage.get_batch(batch_id):
        raise HTTPException(404, "batch not found")

    if fmt == "csv":
        paths = export.export_csv(batch_id)
        return {"paths": paths}
    if fmt == "excel":
        path = export.export_excel(batch_id)
        return FileResponse(path, filename=os.path.basename(path))
    if fmt == "pdf":
        path = export.export_pdf(batch_id)
        return FileResponse(path, filename=os.path.basename(path))
    raise HTTPException(400, "unsupported format, use csv|excel|pdf")
