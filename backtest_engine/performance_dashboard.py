"""Strategy Performance Dashboard: a pure read-only DISPLAY/CALCULATION
layer. It never runs a backtest, never touches the Backtest Engine, the
Walk-Forward Testing engine, or Paper Trading, and never blocks, deletes,
or auto-removes a strategy -- it only reads what those systems already
computed and stored (backtest_results in the database, and
walk_forward_status in the strategy's own meta.json) and combines them
into one simple verdict a non-trader can read at a glance.

FOUR FACTORS -- ALL must pass for GREEN; any single failure means RED,
and the specific failing factor(s) are named with their real numbers
(never just "RED", the CEO must never have to guess why):
  1. Expectancy (average $ profit/loss per trade, POOLED across every
     symbol tested in the strategy's most recent completed backtest --
     total dollar PnL / total trade count, not an average-of-per-symbol-
     averages, so a handful of thin-sample symbols can't skew it) > 0.
  2. Profit Factor (gross profit / gross loss, averaged across tested
     symbols -- the same figure backtest_engine.reports.generate_report()
     already reports as avg_profit_factor) >= 1.3.
  3. Trade count (total, pooled across every symbol tested) >= 100 --
     fewer trades are statistically unreliable to judge at all.
  4. Walk-Forward Testing status == "PASS" (backtest_engine.
     strategy_library's meta.json "walk_forward_status", written by
     automation_pipeline.walk_forward.run_walk_forward_test -- see that
     module for what PASS/FAIL means there).

Thresholds (profit factor >= 1.3, trade count >= 100) are exactly what
the CEO specified for this feature -- not this module's own defaults.

A factor with NO data yet (no completed backtest at all, or Walk-Forward
never run) is reported as its own distinct "not available" state and
still counts as a failure toward RED -- "no evidence of passing" is not
the same claim as "GREEN", so it's never silently treated as one.
"""

from backtest_engine import strategy_library
from data_engine import storage

MIN_PROFIT_FACTOR = 1.3
MIN_TRADE_COUNT = 100

_FACTOR_ORDER = ("expectancy", "profit_factor", "trade_count", "walk_forward")
_FACTOR_LABELS = {
    "expectancy": "Expectancy (avg profit/loss per trade)",
    "profit_factor": "Profit Factor",
    "trade_count": "Trade Count",
    "walk_forward": "Walk-Forward Test",
}


def find_last_completed_batch(strategy_name, recent_batches=None):
    """The strategy's most recent COMPLETED backtest batch, or None.
    Batches are matched by strategy NAME (the same join key
    sindhu_web/api/backtesting.py's _strategy_last_batch_result already
    uses), since that's how backtest_batches rows are stored.
    `recent_batches` lets a caller iterating many strategies fetch the
    batch list once and reuse it, exactly like that existing endpoint
    already does -- avoids one DB round trip per strategy."""
    batches = recent_batches if recent_batches is not None else storage.list_recent_batches(limit=100)
    for batch in batches:
        if batch["strategy_name"] == strategy_name and batch["status"] == "completed":
            return batch
    return None


def _pooled_batch_metrics(batch):
    """Trade count, dollar expectancy, and average profit factor pooled
    across every symbol completed in this batch. Returns None if the
    batch has no completed, metric-bearing results yet."""
    results = storage.get_batch_results(batch["batch_id"])
    completed = [r for r in results if r["status"] == "completed" and r["metrics"]]
    if not completed:
        return None

    total_trades = sum(r["metrics"]["total_trades"] for r in completed)
    initial_balance = (batch.get("settings") or {}).get("initial_balance")
    total_pnl = (
        sum(r["metrics"]["final_balance"] - initial_balance for r in completed)
        if initial_balance is not None else None
    )
    expectancy = (total_pnl / total_trades) if (total_pnl is not None and total_trades) else None

    profit_factors = [r["metrics"]["profit_factor"] for r in completed if r["metrics"]["profit_factor"] is not None]
    avg_profit_factor = sum(profit_factors) / len(profit_factors) if profit_factors else None

    return {
        "batch_id": batch["batch_id"], "symbols_tested": len(completed),
        "total_trades": total_trades, "total_pnl": round(total_pnl, 4) if total_pnl is not None else None,
        "expectancy": round(expectancy, 4) if expectancy is not None else None,
        "profit_factor": round(avg_profit_factor, 4) if avg_profit_factor is not None else None,
    }


def _check_expectancy(pooled):
    if pooled is None or pooled["expectancy"] is None:
        return {"factor": "expectancy", "passed": False, "available": False,
                "value": None, "requirement": "> 0",
                "detail": "No completed backtest found yet -- expectancy can't be judged without one."}
    passed = pooled["expectancy"] > 0
    return {"factor": "expectancy", "passed": passed, "available": True,
            "value": pooled["expectancy"], "requirement": "> 0",
            "detail": f"${pooled['expectancy']:.4f} average profit/loss per trade "
                      f"({'positive' if passed else 'negative'})."}


def _check_profit_factor(pooled):
    if pooled is None or pooled["profit_factor"] is None:
        return {"factor": "profit_factor", "passed": False, "available": False,
                "value": None, "requirement": f">= {MIN_PROFIT_FACTOR}",
                "detail": "No completed backtest found yet -- profit factor can't be judged without one."}
    passed = pooled["profit_factor"] >= MIN_PROFIT_FACTOR
    return {"factor": "profit_factor", "passed": passed, "available": True,
            "value": pooled["profit_factor"], "requirement": f">= {MIN_PROFIT_FACTOR}",
            "detail": f"{pooled['profit_factor']:.4f} (needs >= {MIN_PROFIT_FACTOR})."}


def _check_trade_count(pooled):
    if pooled is None:
        return {"factor": "trade_count", "passed": False, "available": False,
                "value": None, "requirement": f">= {MIN_TRADE_COUNT}",
                "detail": "No completed backtest found yet -- trade count is 0."}
    trades = pooled["total_trades"]
    passed = trades >= MIN_TRADE_COUNT
    return {"factor": "trade_count", "passed": passed, "available": True,
            "value": trades, "requirement": f">= {MIN_TRADE_COUNT}",
            "detail": f"{trades} trades tested (needs >= {MIN_TRADE_COUNT})"
                      + ("" if passed else " -- too few to be statistically reliable.")}


def _check_walk_forward(meta):
    status = meta.get("walk_forward_status")
    if status is None:
        return {"factor": "walk_forward", "passed": False, "available": False,
                "value": None, "requirement": "== PASS",
                "detail": "Walk-Forward Test has not been run yet for this strategy."}
    passed = status == "PASS"
    wf_result = meta.get("walk_forward_result") or {}
    reason = wf_result.get("reason")
    detail = f"Walk-Forward status: {status}."
    if reason:
        detail += f" {reason}"
    return {"factor": "walk_forward", "passed": passed, "available": True,
            "value": status, "requirement": "== PASS", "detail": detail}


def evaluate_strategy_performance(strategy_id, recent_batches=None):
    """Returns:
    {"verdict": "GREEN"|"RED", "label": "Aage Badhao"|"Abhi Ready Nahi",
     "factors": [each of the 4 checks above, in a fixed order],
     "failed_factors": [short human strings, only the ones that failed],
     "batch_id": str|None, "symbols_tested": int|None}

    Never raises for a strategy that simply has no data yet -- that's a
    normal, expected RED, not an error."""
    try:
        cfg = strategy_library.load(strategy_id)
    except FileNotFoundError:
        return None

    meta = strategy_library._read_meta(strategy_id)
    batch = find_last_completed_batch(cfg.name, recent_batches=recent_batches)
    pooled = _pooled_batch_metrics(batch) if batch else None

    checks = {
        "expectancy": _check_expectancy(pooled),
        "profit_factor": _check_profit_factor(pooled),
        "trade_count": _check_trade_count(pooled),
        "walk_forward": _check_walk_forward(meta),
    }
    factors = [checks[name] for name in _FACTOR_ORDER]
    all_passed = all(f["passed"] for f in factors)

    failed_factors = []
    for f in factors:
        if f["passed"]:
            continue
        label = _FACTOR_LABELS[f["factor"]]
        if not f["available"]:
            failed_factors.append(f"{label}: not available yet")
        else:
            failed_factors.append(f"{label}: {f['detail']}")

    return {
        "verdict": "GREEN" if all_passed else "RED",
        "label": "Aage Badhao" if all_passed else "Abhi Ready Nahi",
        "factors": factors,
        "failed_factors": failed_factors,
        "batch_id": pooled["batch_id"] if pooled else None,
        "symbols_tested": pooled["symbols_tested"] if pooled else None,
    }
