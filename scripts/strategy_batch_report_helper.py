"""Shared aggregation helper for the New Batch 5 (9-strategy) build --
pools a completed run_mtf_batch's per-symbol results into the same report
shape for every strategy, and applies the EXISTING Why-Win/Why-Loss
classifier (paper_trading.insights.classify_win_loss) to every real trade
instead of inventing new analysis. Not a new metrics engine: every number
here is either read directly from backtest_engine.metrics.compute_metrics'
own per-symbol output (already stored via run_mtf_batch) or a plain sum/
worst-case pool across symbols of those same numbers.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_engine import storage
from paper_trading.insights import classify_win_loss


def pooled_report(batch_id):
    results = storage.get_batch_results(batch_id)
    completed = [r for r in results if r["status"] == "completed" and r["metrics"]]
    errored = [r for r in results if r["status"] != "completed"]

    total_trades = sum(r["metrics"]["total_trades"] for r in completed)
    total_wins = sum(r["metrics"]["wins"] for r in completed)
    total_gross_profit = sum(r["metrics"]["gross_profit"] for r in completed)
    total_gross_loss = sum(r["metrics"]["gross_loss"] for r in completed)
    total_net_profit = sum(r["metrics"]["net_profit"] for r in completed)
    worst_drawdown = max((r["metrics"]["max_drawdown_pct"] for r in completed), default=0.0)
    pooled_win_rate = round((total_wins / total_trades * 100), 2) if total_trades else 0.0
    pooled_profit_factor = round((total_gross_profit / total_gross_loss), 4) if total_gross_loss else None

    zero_trade_symbols = [r["symbol"] for r in completed if r["metrics"]["total_trades"] == 0]

    # Why-Win/Why-Loss: reuse the existing per-trade classifier as-is
    # (paper_trading.insights.classify_win_loss), fed with each real
    # backtest trade reshaped into the {status, pnl, exit_reason} it
    # expects -- it never re-runs strategy logic, purely labels the
    # outcome already recorded at close time.
    reason_counts = {}
    for r in completed:
        trades = storage.get_trades(batch_id, r["symbol"], r.get("timeframe"))
        for t in trades:
            pos = {"status": "closed", "pnl": t.get("pnl"), "exit_reason": t.get("exit_reason")}
            tag = classify_win_loss(pos)
            reason_counts[tag] = reason_counts.get(tag, 0) + 1

    return {
        "batch_id": batch_id,
        "symbols_tested": len(completed),
        "symbols_errored": len(errored),
        "errored_symbols": [{"symbol": r["symbol"], "reason": (r.get("metrics") or {}).get("reason") or r.get("status")} for r in errored],
        "zero_trade_symbols": zero_trade_symbols,
        "total_trades": total_trades,
        "win_rate_pct": pooled_win_rate,
        "profit_factor": pooled_profit_factor,
        "total_net_profit": round(total_net_profit, 2),
        "worst_max_drawdown_pct": round(worst_drawdown, 2),
        "why_win_loss_breakdown": reason_counts,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(pooled_report(sys.argv[1]), indent=2))
