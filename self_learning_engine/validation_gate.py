"""Phase 1.6 (mandatory out-of-sample validation gate), 1.7 (25-trade
minimum per period, reusing the project's existing Wilson gate threshold),
and 1.8 (dual filter: minimum 1:2 Risk:Reward AND a genuinely high win
rate, benchmarked against real currently-profitable strategies).

Deliberately pure/testable: this module never runs a backtest itself --
discovery_cycle.py calls backtest_engine.runner.run_mtf_batch twice (once
per period) and passes the resulting batch_id here. Reuses backtest_engine.
performance_dashboard._pooled_batch_metrics for the profit-factor pooling
convention already used everywhere else in this project (a batch's PF is
the average of its completed symbols' own profit_factor, not a single
recomputed gross_profit/gross_loss ratio) -- so this gate's numbers never
silently disagree with what the Strategy Performance Dashboard would show
for the same batch.
"""

from backtest_engine import performance_dashboard as perf_dashboard
from data_engine import storage
from paper_trading import pattern_stats

MIN_TRADES_PER_PERIOD = pattern_stats.MIN_SAMPLE_SIZE  # 25 -- same Wilson gate threshold, never a softer number
MIN_PROFIT_FACTOR = 1.0
MIN_RISK_REWARD = 2.0  # "minimum 1:2"


def compute_period_metrics(batch_id):
    """total_trades, win_rate, profit_factor, avg_risk_reward for one
    completed batch (one discovery/validation period). None if the batch
    has no completed, metric-bearing results at all."""
    batch = storage.get_batch(batch_id)
    if not batch:
        return None
    results = storage.get_batch_results(batch_id)
    completed = [r for r in results if r["status"] == "completed" and r["metrics"]]
    if not completed:
        return None

    total_trades = sum(r["metrics"]["total_trades"] for r in completed)
    wins = sum(r["metrics"]["wins"] for r in completed)
    win_rate = round((wins / total_trades * 100) if total_trades else 0.0, 2)

    pooled = perf_dashboard._pooled_batch_metrics(batch, batch_results_cache={batch_id: results})
    profit_factor = pooled["profit_factor"] if pooled else None

    rrs = [r["metrics"]["risk_reward"] for r in completed if r["metrics"].get("risk_reward") is not None]
    avg_risk_reward = round(sum(rrs) / len(rrs), 4) if rrs else None

    return {
        "batch_id": batch_id, "total_trades": total_trades, "win_rate": win_rate,
        "profit_factor": profit_factor, "avg_risk_reward": avg_risk_reward,
    }


def compute_win_rate_benchmark():
    """Phase 1.8's 'genuinely high win rate, cross-referenced against the
    existing 8-10 profitable strategies' -- never an invented number.
    'Profitable' reuses the EXACT SAME definition paper_trading.telegram_bot.
    _profitability_label already uses for the same phrase elsewhere in this
    project: >= pattern_stats.MIN_SAMPLE_SIZE (25) closed trades AND net
    positive realized PnL. The benchmark is the LOWEST win rate among that
    real set -- 'at least as good as our worst current profitable
    strategy' is the honest, data-driven bar, not a guessed percentage.

    Returns (benchmark_pct, profitable_strategy_count). benchmark_pct is
    None if fewer than 2 strategies currently qualify as profitable (too
    thin a sample to set a bar from)."""
    states = storage.list_paper_account_states()
    profitable_win_rates = []
    for s in states:
        if s["closed_count"] >= pattern_stats.MIN_SAMPLE_SIZE and s["realized_pnl_total"] > 0:
            profitable_win_rates.append(s["win_count"] / s["closed_count"] * 100)
    if len(profitable_win_rates) < 2:
        return None, len(profitable_win_rates)
    return round(min(profitable_win_rates), 2), len(profitable_win_rates)


def evaluate(discovery_metrics, validation_metrics, structural_risk_reward):
    """The combined Phase 1.6/1.7/1.8 gate. Never blends the two periods
    into one number that could hide a failure in either -- both are
    checked, and reported, independently, per Phase 1.6's explicit rule.

    Returns {passed, reasons: [...], discovery_metrics, validation_metrics,
    win_rate_benchmark_pct}."""
    reasons = []

    for label, metrics in (("discovery", discovery_metrics), ("validation", validation_metrics)):
        if metrics is None:
            reasons.append(f"{label} period produced no completed backtest results")
            continue
        if metrics["total_trades"] < MIN_TRADES_PER_PERIOD:
            reasons.append(
                f"{label} period only had {metrics['total_trades']} trades "
                f"(needs >= {MIN_TRADES_PER_PERIOD}, the same Wilson gate threshold used elsewhere)"
            )
        if metrics["profit_factor"] is None or metrics["profit_factor"] < MIN_PROFIT_FACTOR:
            reasons.append(
                f"{label} period profit factor is {metrics['profit_factor']} (needs >= {MIN_PROFIT_FACTOR})"
            )

    if structural_risk_reward is None or structural_risk_reward < MIN_RISK_REWARD:
        reasons.append(f"structural risk:reward is {structural_risk_reward} (needs >= 1:{MIN_RISK_REWARD})")

    benchmark_pct, profitable_count = compute_win_rate_benchmark()
    if benchmark_pct is not None and not reasons:
        for label, metrics in (("discovery", discovery_metrics), ("validation", validation_metrics)):
            if metrics and metrics["win_rate"] < benchmark_pct:
                reasons.append(
                    f"{label} period win rate {metrics['win_rate']}% is below the real-data benchmark "
                    f"{benchmark_pct}% (the lowest win rate among the {profitable_count} currently profitable strategies)"
                )

    return {
        "passed": not reasons,
        "reasons": reasons,
        "discovery_metrics": discovery_metrics,
        "validation_metrics": validation_metrics,
        "win_rate_benchmark_pct": benchmark_pct,
        "profitable_strategy_count_for_benchmark": profitable_count,
    }
