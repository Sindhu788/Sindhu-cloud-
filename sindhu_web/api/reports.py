import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from data_engine import storage
from backtest_engine.reports import generate_report, quick_batch_summary
from backtest_engine import export
from backtest_engine.diagnostics import plain_language_diagnosis

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
            # Present when the automation pipeline (Part 2) ran an
            # optimization pass involving this batch, either as the
            # original or the optimized side -- lets the Backtest History
            # page show the original-vs-optimized comparison inline
            # without a separate request per row.
            s["optimization"] = storage.get_optimization_for_batch(b["batch_id"])
            summaries.append(s)
    return {"batches": summaries}


class RenameBatchRequest(BaseModel):
    display_name: str


@router.post("/api/backtest-history/{batch_id}/rename")
def rename_batch(batch_id: str, req: RenameBatchRequest):
    """Purely a display label (Part 3) -- never touches strategy_name,
    settings, or any trade/result row for this batch."""
    name = req.display_name.strip()
    if not name:
        raise HTTPException(400, "Name cannot be empty.")
    if not storage.get_batch(batch_id):
        raise HTTPException(404, "Batch not found.")
    storage.set_batch_display_name(batch_id, name)
    return {"ok": True, "batch_id": batch_id, "display_name": name}


@router.get("/api/backtest-history/{batch_id}/comparison")
def get_comparison(batch_id: str):
    """Single shared source for the Original vs Optimized comparison table
    -- used by both the Backtest History page and the SINDHU CEO
    Backtesting card, so the two views can never show conflicting numbers
    (per the standing "SINDHU CEO stays current with every feature" rule).
    Works whether `batch_id` is the original or the optimized side, since
    storage.get_optimization_for_batch() already matches either.
    has_optimization=False (with no other fields) means this batch was
    never run through the auto-optimizer -- original-only, nothing to
    compare."""
    opt = storage.get_optimization_for_batch(batch_id)
    if not opt:
        return {"has_optimization": False}

    original = quick_batch_summary(opt["original_batch_id"])
    optimized = quick_batch_summary(opt["optimized_batch_id"]) if opt["optimized_batch_id"] else None

    why = None
    if opt["winner"] == "optimized" and optimized and original:
        reasons = []
        if optimized.get("total_pnl") is not None and original.get("total_pnl") is not None \
                and optimized["total_pnl"] > original["total_pnl"]:
            reasons.append("higher total PnL")
        if optimized.get("max_drawdown_pct") is not None and original.get("max_drawdown_pct") is not None \
                and optimized["max_drawdown_pct"] < original["max_drawdown_pct"]:
            reasons.append("lower max drawdown")
        why = f"Optimized won -- {' and '.join(reasons)}" if reasons else "Optimized won -- higher total PnL on the full re-backtest"
    elif opt["winner"] == "original" and optimized:
        why = "Original won -- the optimized candidate did not beat it on the full re-backtest"
    elif opt["winner"] == "original":
        why = "Original won -- no parameter combination beat it on the fast screen, so no full re-backtest was run"

    return {
        "has_optimization": True,
        "winner": opt["winner"],
        "why": why,
        "original": original,
        "optimized": optimized,
        "params_changed": opt["params_changed"],
        "candidates_tried": len(opt["candidates_tried"]),
        "created_at": opt["created_at"],
    }


@router.get("/api/reports/best-worst/strategies")
def best_worst_strategies():
    # Uses quick_batch_summary() (not generate_report()) -- this only needs
    # avg_profit_pct per batch, so there's no reason to pay generate_report()'s
    # full per-trade session-analysis scan (20-45s on a large batch) once for
    # every completed batch in the list.
    #
    # Ranks each strategy by its MOST RECENT completed batch only, not an
    # average across every batch ever run for it -- real bug fixed here:
    # averaging in every historical batch let one ancient, since-superseded
    # batch (run under a long-fixed engine bug that let balance compound
    # without any realistic cap -- one real batch's stored profit_pct was
    # 425,679,667,191.65%) permanently poison the displayed "Top Strategies
    # by Profit" and "Best Strategy" label, even though that batch has
    # nothing to do with how the strategy performs today. Every OTHER view
    # of "how is this strategy doing" (Overview's PnL/win-rate cards,
    # Backtest History's per-row numbers) already means "the latest run" --
    # this endpoint was the one place still silently blending in stale
    # history, which is what made it look inconsistent with Backtest
    # History. Old batches are never deleted (see storage.py's "never
    # delete, only archive" pattern throughout) -- they simply aren't used
    # for THIS "how is it doing right now" ranking anymore.
    batches = storage.list_recent_batches(limit=200)
    latest_per_strategy = {}
    completed_batch_counts = {}
    for b in batches:
        if b["status"] != "completed":
            continue
        name = b["strategy_name"]
        completed_batch_counts[name] = completed_batch_counts.get(name, 0) + 1
        # list_recent_batches is already newest-first, so the first
        # completed batch seen per strategy name is its latest one --
        # everything below is computed from THAT one batch only, never
        # blended with older ones (see comment above).
        if name in latest_per_strategy:
            continue
        try:
            summary = quick_batch_summary(b["batch_id"])
        except Exception:
            continue
        if not summary:
            continue
        latest_per_strategy[name] = summary

    ranked = sorted(
        (
            {
                "strategy": name, "avg_profit_pct": summary["avg_profit_pct"],
                "total_pnl": summary["total_pnl"], "batch_id": summary["batch_id"],
                "batches": completed_batch_counts.get(name, 1),
            }
            for name, summary in latest_per_strategy.items()
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
    backtest itself ran and stored alongside the batch.

    Each report also carries a `diagnosis` plain-English sentence (Part 2:
    auto-surfaced 0-trade diagnosis) computed here once so Backtest History
    and the SINDHU CEO Backtesting card show the exact same wording for the
    exact same data -- neither builds its own copy of this logic."""
    if not storage.get_batch(batch_id):
        raise HTTPException(404, "batch not found")
    reports = storage.list_condition_reports(batch_id)
    for r in reports:
        r["diagnosis"] = plain_language_diagnosis(r["report"])
    return {"reports": reports}


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
