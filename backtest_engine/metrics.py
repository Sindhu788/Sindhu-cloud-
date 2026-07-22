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


def compute_metrics(trades, equity_curve, initial_balance):
    total_trades = len(trades)
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]

    win_rate = (len(wins) / total_trades * 100) if total_trades else 0.0
    final_balance = equity_curve[-1] if equity_curve else initial_balance
    profit_pct = ((final_balance - initial_balance) / initial_balance * 100) if initial_balance else 0.0

    avg_win = (sum(t["pnl"] for t in wins) / len(wins)) if wins else 0.0
    avg_loss = (sum(t["pnl"] for t in losses) / len(losses)) if losses else 0.0

    gross_profit = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))
    net_profit = gross_profit - gross_loss
    profit_factor = (gross_profit / gross_loss) if gross_loss else None
    risk_reward = (avg_win / abs(avg_loss)) if avg_loss else None
    # Expectancy: average $ PnL per trade, win rate and avg win/loss already
    # baked in ((win% * avg_win) - (loss% * |avg_loss|) is mathematically
    # identical to net_profit / total_trades -- computed the direct way to
    # avoid any rounding drift between the two).
    expectancy = (net_profit / total_trades) if total_trades else 0.0
    total_commission = sum(t.get("commission_cost") or 0.0 for t in trades)
    total_slippage = sum(t.get("slippage_cost") or 0.0 for t in trades)
    total_spread = sum(t.get("spread_cost") or 0.0 for t in trades)

    return {
        "total_trades": total_trades,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate, 2),
        "profit_pct": round(profit_pct, 2),
        "final_balance": round(final_balance, 2),
        "max_drawdown_pct": round(_max_drawdown_pct(equity_curve), 2),
        "avg_win": round(avg_win, 4),
        "avg_loss": round(avg_loss, 4),
        "gross_profit": round(gross_profit, 4),
        "gross_loss": round(gross_loss, 4),
        "net_profit": round(net_profit, 4),
        "expectancy": round(expectancy, 4),
        "profit_factor": round(profit_factor, 4) if profit_factor is not None else None,
        "risk_reward": round(risk_reward, 4) if risk_reward is not None else None,
        "total_commission": round(total_commission, 4),
        "total_slippage": round(total_slippage, 4),
        "total_spread": round(total_spread, 4),
    }
