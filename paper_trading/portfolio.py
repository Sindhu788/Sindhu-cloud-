"""Portfolio & Capital Intelligence (Group 5): aggregate views ACROSS every
active strategy's independent book, built entirely by reading data these
already-verified features produce (Correlation Warning, Risk Analytics,
paper_positions) -- nothing here duplicates that logic or touches the
trading loop.

1. Portfolio Analytics Engine: total exposure/open risk/combined PnL/a
   correlation-based diversification indicator.
2. Portfolio Risk Engine: one combined risk score from every strategy's
   own Sharpe/Max Drawdown (see insights.compute_risk_metrics).
3. Exposure Manager: total risk allocated per COIN across ALL strategies
   combined (the existing 5-coin cap in risk_manager.py is PER STRATEGY;
   this is the cross-strategy view management doesn't otherwise have).
"""

from data_engine import storage
from paper_trading import config as pt_config
from paper_trading import insights, correlation


def compute_portfolio_analytics(exchange):
    """Aggregate exposure/risk/PnL across every strategy's open positions
    and realized PnL. Degrades gracefully to zeros with no open positions."""
    open_positions = storage.get_open_paper_positions(exchange)
    total_exposure = sum(abs(p["entry_price"] * p["size"]) for p in open_positions)
    total_open_risk = sum(p.get("risk_amount") or 0 for p in open_positions)

    states = storage.list_paper_account_states()
    combined_realized_pnl = sum(s["realized_pnl_total"] for s in states)

    warnings = correlation.detect_warnings(exchange)
    symbols_in_warnings = set()
    for w in warnings:
        symbols_in_warnings.update(w["symbols"])
    positions_in_warned_symbols = sum(1 for p in open_positions if p["symbol"] in symbols_in_warnings)
    # Diversification indicator: what share of currently-open positions sit
    # in a symbol that's part of an active correlation warning right now.
    # 0% = fully diversified (no flagged overlap), higher = more of the
    # portfolio is concentrated in assets that tend to move together.
    concentration_pct = round(positions_in_warned_symbols / len(open_positions) * 100, 1) if open_positions else 0.0

    return {
        "open_position_count": len(open_positions),
        "total_exposure": round(total_exposure, 2),
        "total_open_risk": round(total_open_risk, 2),
        "combined_realized_pnl": round(combined_realized_pnl, 2),
        "correlation_concentration_pct": concentration_pct,
        "correlation_warning_count": len(warnings),
    }


def compute_portfolio_risk_score(strategy_ids, since=None):
    """Single combined risk score from every strategy's OWN Sharpe/Max
    Drawdown (paper_trading.insights.compute_risk_metrics -- no new risk
    math invented here, purely an aggregation of already-computed numbers).

    Aggregation method (documented, not a hidden black box):
      - avg_sharpe: simple mean of every strategy's Sharpe Ratio that has
        enough data to have one. A strategy with too few trades to compute
        a Sharpe is excluded, not treated as 0 (would unfairly punish new
        strategies rather than reflect real risk).
      - worst_drawdown_pct: the MAXIMUM (worst) Max Drawdown % across all
        strategies, not an average -- portfolio risk should reflect the
        worst thing currently happening, not be smoothed away by strategies
        having a good day. Strategies aren't assumed perfectly uncorrelated,
        so averaging away one strategy's bad drawdown would understate risk.
      - risk_score (0-100, higher = healthier): starts at 100, subtracts
        2 points per 1% of worst_drawdown_pct (capped) and 10 points per
        each point avg_sharpe is below zero. This is a simple, transparent,
        documented heuristic for an at-a-glance number -- not a claim to
        any industry-standard "portfolio risk score" formula.
    """
    sharpes, drawdowns, contributing = [], [], 0
    for sid in strategy_ids:
        m = insights.compute_risk_metrics(sid, since=since)
        if m["sharpe_ratio"] is not None:
            sharpes.append(m["sharpe_ratio"])
        if m["max_drawdown_pct"] is not None:
            drawdowns.append(m["max_drawdown_pct"])
        if m["sample_size"] >= 2:
            contributing += 1

    if not sharpes and not drawdowns:
        return {"risk_score": None, "avg_sharpe": None, "worst_drawdown_pct": None,
                "strategies_with_data": 0, "reason": "no strategy has enough closed trades yet"}

    avg_sharpe = round(sum(sharpes) / len(sharpes), 3) if sharpes else None
    worst_drawdown = round(max(drawdowns), 2) if drawdowns else 0.0

    score = 100.0
    score -= min(worst_drawdown * 2, 60)
    if avg_sharpe is not None and avg_sharpe < 0:
        score -= min(abs(avg_sharpe) * 10, 40)
    score = round(max(0.0, min(100.0, score)), 1)

    return {
        "risk_score": score, "avg_sharpe": avg_sharpe, "worst_drawdown_pct": worst_drawdown,
        "strategies_with_data": contributing,
    }


def compute_coin_exposure(exchange):
    """Total risk/notional allocated per COIN across every strategy
    combined -- the cross-strategy view risk_manager's per-strategy 5-coin
    cap doesn't provide. Sorted by total risk descending (biggest
    concentration first)."""
    open_positions = storage.get_open_paper_positions(exchange)
    by_symbol = {}
    for p in open_positions:
        row = by_symbol.setdefault(p["symbol"], {
            "symbol": p["symbol"], "position_count": 0, "strategy_ids": set(),
            "total_notional": 0.0, "total_risk": 0.0,
        })
        row["position_count"] += 1
        row["strategy_ids"].add(p.get("strategy_id") or "lessons")
        row["total_notional"] += abs(p["entry_price"] * p["size"])
        row["total_risk"] += p.get("risk_amount") or 0

    result = []
    for row in by_symbol.values():
        result.append({
            "symbol": row["symbol"],
            "position_count": row["position_count"],
            "strategy_count": len(row["strategy_ids"]),
            "total_notional": round(row["total_notional"], 2),
            "total_risk": round(row["total_risk"], 2),
        })
    result.sort(key=lambda r: r["total_risk"], reverse=True)
    return result
