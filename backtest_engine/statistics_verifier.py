"""Final Audit (BACKTESTING_MASTER_SPEC.md Engine Health Report --
Statistics Verification): independently RE-derives win rate, profit
factor, net profit, and max drawdown straight from the trade list and
equity curve, then diffs against whatever metrics.compute_metrics()
reported -- the same "never trust the same code path that produced the
number to also check it" principle used by trade_validator and
data_quality. Catches a metrics-layer bug (e.g. a wrong win/loss
partition, a drift between profit_pct and the trade-level PnL sum) that
compute_metrics() itself could never catch on its own.
"""


def _max_drawdown_pct(equity_curve):
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        if peak > 0:
            dd = (peak - eq) / peak * 100
            if dd > max_dd:
                max_dd = dd
    return max_dd


def verify_statistics(trades, equity_curve, initial_balance, reported_metrics, tolerance_pct=0.01):
    """Returns a list of mismatch strings (empty = statistics are
    self-consistent). Recomputation is a plain, independent re-derivation
    -- deliberately NOT calling metrics.compute_metrics()."""
    issues = []
    if reported_metrics is None:
        return ["no metrics were reported to verify"]

    total_trades = len(trades)
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    win_rate = (len(wins) / total_trades * 100) if total_trades else 0.0
    final_balance = equity_curve[-1] if equity_curve else initial_balance
    profit_pct = ((final_balance - initial_balance) / initial_balance * 100) if initial_balance else 0.0
    gross_profit = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))
    net_profit = gross_profit - gross_loss
    max_dd = _max_drawdown_pct(equity_curve)

    def _check(field, recomputed, tol=tolerance_pct):
        reported = reported_metrics.get(field)
        if reported is None:
            issues.append(f"{field}: reported metrics has no value, recomputed {recomputed}")
            return
        if abs(reported - recomputed) > max(abs(recomputed) * (tol / 100.0), 1e-6):
            issues.append(f"{field}: reported={reported} but independently recomputed={recomputed}")

    _check("total_trades", total_trades)
    _check("wins", len(wins))
    _check("losses", len(losses))
    _check("win_rate", round(win_rate, 2))
    _check("final_balance", round(final_balance, 2))
    _check("profit_pct", round(profit_pct, 2))
    _check("gross_profit", round(gross_profit, 4))
    _check("gross_loss", round(gross_loss, 4))
    _check("net_profit", round(net_profit, 4))
    _check("max_drawdown_pct", round(max_dd, 2))

    # net_profit must independently reconcile with balance movement -- the
    # single most important cross-check (Requirement 12: prevent incorrect
    # balance updates / double counting).
    actual_balance_change = final_balance - initial_balance
    if abs(actual_balance_change - net_profit) > max(abs(net_profit) * (tolerance_pct / 100.0), 1e-6):
        issues.append(
            f"net_profit ({net_profit}) does not reconcile with the actual balance change "
            f"({actual_balance_change}) -- possible double counting or a missed PnL update"
        )

    return issues
