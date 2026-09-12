"""Cross-strategy aggregate summary (each strategy's latest completed
backtest batch, aggregated) -- shared by sindhu_web/api/home.py (the Home
dashboard's /api/strategy-summary) and sindhu_web/api/strategy_lifecycle.py
(the Strategy Lifecycle page).

Master Task: Full Strategy Count Audit + Cloud Verification, Part 2:
extracted out of home.py into its own tiny module so strategy_lifecycle.py
(now also mounted on cloud_runtime/app.py, to fix the cloud dashboard's
Profitable/Under-Evaluation split always showing empty) does not have to
import home.py itself -- home.py pulls in knowledge_engine.*/backtest_engine.
reports at module load, which cloud_runtime/app.py's own tests explicitly
forbid importing there. This module only ever touches strategy_library/
storage/job_manager, none of which are on that forbidden list.
"""
from datetime import datetime, timezone

from backtest_engine import strategy_library
from data_engine import storage
from sindhu_web.jobs import job_manager


def compute_strategy_summary():
    active = [s for s in strategy_library.list_all() if not s.get("archived")]
    # Fix, 2026-09-12: same incident as paper_trading.signal_tracker's
    # _latest_batch_ids_by_name -- this used to call
    # latest_completed_batch_for_strategy_name() once per strategy in the
    # loop below, and the lightweight cloud runner's curated Postgres schema
    # deliberately excludes backtest_batches (see data_engine/db_backend.py's
    # POSTGRES_SCHEMA docstring), so every one of those calls threw
    # UndefinedTable, uncaught, taking down the whole /api/strategy-lifecycle
    # response (and the Strategy Lifecycle page along with it) on every
    # cloud request. Batched into ONE query with the same safe "nothing
    # exists yet" fallback signal_tracker already uses.
    try:
        batch_by_name = storage.latest_completed_batches_for_strategy_names([s["name"] for s in active])
    except Exception:
        batch_by_name = {}

    rows = []
    for s in active:
        batch_id = batch_by_name.get(s["name"])
        if not batch_id:
            continue
        results = storage.get_batch_results(batch_id)
        if not results:
            continue
        total_trades = sum(r["metrics"]["total_trades"] for r in results)
        if not total_trades:
            continue
        wins = sum(r["metrics"]["wins"] for r in results)
        net = sum(r["metrics"]["net_profit"] for r in results)
        gross_profit = sum(r["metrics"]["gross_profit"] for r in results)
        gross_loss = sum(abs(r["metrics"]["gross_loss"]) for r in results)
        pf = (gross_profit / gross_loss) if gross_loss else None
        worst_dd = max((r["metrics"].get("max_drawdown_pct", 0) for r in results), default=None)
        rows.append({
            "id": s["id"], "name": s["name"],
            "trades": total_trades, "win_rate": round(100 * wins / total_trades, 2),
            "net_pnl": round(net, 2), "profit_factor": round(pf, 4) if pf else None,
            "profitable": bool(pf and pf > 1.0), "batch_id": batch_id,
            "worst_drawdown_pct": round(worst_dd, 2) if worst_dd is not None else None,
        })

    total_trades_all = sum(r["trades"] for r in rows)
    weighted_win_rate = (
        round(sum(r["win_rate"] * r["trades"] for r in rows) / total_trades_all, 2)
        if total_trades_all else None
    )
    aggregate_net_pnl = round(sum(r["net_pnl"] for r in rows), 2)
    profitable_count = sum(1 for r in rows if r["profitable"])

    by_pf = sorted((r for r in rows if r["profit_factor"] is not None), key=lambda r: r["profit_factor"])
    best = by_pf[-1] if by_pf else None
    worst = by_pf[0] if by_pf else None

    optimizer_running = any(
        j.kind == "backtest" and j.status == "running" for j in job_manager.list_jobs()
    )

    return {
        "total_strategies": len(rows),
        "profitable_count": profitable_count,
        "aggregate_trade_weighted_win_rate": weighted_win_rate,
        "aggregate_net_pnl": aggregate_net_pnl,
        "best": best, "worst": worst,
        "strategies": sorted(rows, key=lambda r: -(r["profit_factor"] or -999)),
        "optimizer_in_progress": optimizer_running,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def compute_backtest_metrics_for_strategy(strategy_id):
    """Grand Master Prompt, Phase 2.2: the 7 named comparison metrics (Win
    Rate, Profit Factor, Max Drawdown, Avg Win, Avg Loss, Total Trades, Net
    PnL) for ONE strategy's latest completed backtest batch -- backs the
    Strategy Comparison ("pick any two") view. avg_win/avg_loss need real
    per-trade data (not in the per-coin/timeframe result rows the rest of
    this module aggregates), so this reads storage.get_trades(batch_id)
    once, same source already used by strategy_lifecycle.py's Failure
    Reason Report."""
    try:
        meta = strategy_library.get_meta(strategy_id)
    except FileNotFoundError:
        return None
    if not meta:
        return None
    batch_id = storage.latest_completed_batch_for_strategy_name(meta["name"])
    if not batch_id:
        return {"available": False}
    results = storage.get_batch_results(batch_id)
    if not results:
        return {"available": False}

    total_trades = sum(r["metrics"]["total_trades"] for r in results)
    if not total_trades:
        return {"available": False}
    wins = sum(r["metrics"]["wins"] for r in results)
    net = sum(r["metrics"]["net_profit"] for r in results)
    gross_profit = sum(r["metrics"]["gross_profit"] for r in results)
    gross_loss = sum(abs(r["metrics"]["gross_loss"]) for r in results)
    pf = (gross_profit / gross_loss) if gross_loss else None
    worst_dd = max((r["metrics"].get("max_drawdown_pct", 0) for r in results), default=None)

    trades = storage.get_trades(batch_id)
    win_pnls = [t["pnl"] for t in trades if (t["pnl"] or 0) > 0]
    loss_pnls = [t["pnl"] for t in trades if (t["pnl"] or 0) < 0]
    avg_win = (sum(win_pnls) / len(win_pnls)) if win_pnls else 0.0
    avg_loss = (sum(loss_pnls) / len(loss_pnls)) if loss_pnls else 0.0

    return {
        "available": True,
        "batch_id": batch_id,
        "total_trades": total_trades,
        "win_rate_pct": round(100 * wins / total_trades, 2),
        "net_pnl": round(net, 2),
        "profit_factor": round(pf, 4) if pf else None,
        "max_drawdown_pct": round(worst_dd, 2) if worst_dd is not None else None,
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
    }
