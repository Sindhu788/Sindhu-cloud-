"""Slippage Sensitivity Test (Grand Feature Expansion, Phase 3 Feature 18):
how quickly does a strategy's edge break down if real-world slippage turns
out worse than assumed? Distinct from backtest_engine/stress_test.py
(which re-runs a strategy against its own worst historical VOLATILITY
week) -- this varies a cost ASSUMPTION, not the market data.

Reuses the real, already-recorded trades from a completed batch --
recorded entry_price/exit_price already reflect the backtest's OWN
slippage assumption (see backtest_engine.engine._apply_slippage), so this
applies an EXTRA incremental slippage on top via the exact same directional
formula (never re-invented) and recomputes PnL, rather than re-running the
full simulation. Purely read-only reporting -- never re-runs, modifies, or
invalidates the original backtest."""

from backtest_engine.engine import _apply_slippage
from data_engine import storage

# 0% (the baseline, already-recorded result) up to an extra 1% slippage
# per fill -- 1% one-way is already a large, clearly-unrealistic-for-most-
# liquid-pairs assumption, so this range comfortably brackets "still fine"
# through "clearly broken" for a typical strategy.
DEFAULT_EXTRA_SLIPPAGE_LEVELS = (0.0, 0.001, 0.002, 0.005, 0.01)


def run_slippage_sensitivity_test(batch_id, extra_slippage_levels=DEFAULT_EXTRA_SLIPPAGE_LEVELS):
    trades = storage.get_trades(batch_id)
    closed = [t for t in trades if t.get("exit_price") is not None and t.get("pnl") is not None]
    if not closed:
        return {"batch_id": batch_id, "levels": [], "trade_count": 0,
                "reason": "no closed trades in this batch to test"}

    levels = []
    for extra_pct in extra_slippage_levels:
        total_pnl = 0.0
        wins = 0
        for t in closed:
            side = t["side"]
            entry = _apply_slippage(t["entry_price"], side, False, extra_pct)
            exit_price = _apply_slippage(t["exit_price"], side, True, extra_pct)
            pnl = (exit_price - entry) * t["size"] if side == "long" else (entry - exit_price) * t["size"]
            total_pnl += pnl
            if pnl > 0:
                wins += 1
        levels.append({
            "extra_slippage_pct": round(extra_pct * 100, 3),
            "total_pnl": round(total_pnl, 2),
            "win_rate": round(wins / len(closed) * 100, 1),
        })

    baseline_pnl = levels[0]["total_pnl"]
    breakeven_level = next((lvl["extra_slippage_pct"] for lvl in levels if lvl["total_pnl"] <= 0), None)

    return {
        "batch_id": batch_id, "trade_count": len(closed),
        "levels": levels, "baseline_pnl": baseline_pnl,
        "breakeven_extra_slippage_pct": breakeven_level,
        "fragile": breakeven_level is not None and breakeven_level <= 0.5,
    }
