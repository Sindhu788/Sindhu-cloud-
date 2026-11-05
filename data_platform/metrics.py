"""Trade metrics with ONE clear definition each (Day 6 Step 5). numpy only (must also import in the CI/cloud venv).

Unit of analysis = a POSITION (one entry), not a leg. The backtest engine can close one entry in two legs (partial take-profit + remainder);
Day 5 counted every leg as an independent trade, which (a) inflated the trade count, (b) changed win rate / profit factor, and (c) made the
R-multiple average dominated by the small-risk remainder legs (Daily Liquidity Scalping: t = +11.5 with a negative dollar result).

Definitions (all NET of costs; `pnl` in the stored trades is already net of commission, slippage and spread):
- position pnl      = sum of leg pnl;  position risk = sum of leg risk_amount (the money risked at entry)
- R multiple        = position pnl / position risk
- profit factor     = sum of winning position pnl / sum of losing position pnl (inf if no loss and some profit, 0.0 if no trades or all zero)
- win rate          = share of positions with pnl > 0
- expectancy        = mean position pnl (money) ; expectancy_R = mean R
- t-statistic       = mean(R) / (std(R, ddof=1) / sqrt(n)); None when n < 3 or std == 0
- max drawdown      = largest peak-to-trough fall of the cumulative position pnl, positions ordered by exit time
"""
import math

import numpy as np

COST_KEYS = ("commission_cost", "slippage_cost", "spread_cost")


def aggregate_positions(legs):
    """legs: list of dicts (symbol optional) with side, entry_time, exit_time, pnl, risk_amount, cost keys. Returns positions sorted by exit_time."""
    pos = {}
    for t in legs:
        pos.setdefault((t.get("symbol"), t["side"], t["entry_time"]), []).append(t)
    out = []
    for (sym, side, et), ls in pos.items():
        p = {"symbol": sym, "side": side, "entry_time": et, "exit_time": max(l["exit_time"] for l in ls),
             "pnl": float(sum(l["pnl"] for l in ls)), "risk_amount": float(sum(l.get("risk_amount") or 0.0 for l in ls)), "legs": len(ls),
             "entry_price": ls[0].get("entry_price"), "exit_price": ls[-1].get("exit_price")}
        for k in COST_KEYS:
            p[k] = float(sum(l.get(k) or 0.0 for l in ls))
        p["ret"] = _position_return(ls)
        out.append(p)
    out.sort(key=lambda x: (x["exit_time"], x["entry_time"]))
    return out


def _position_return(legs):
    """Risk-weighted gross return of a position as a fraction (side-adjusted, from FILL prices, so slippage and spread are inside; commission is not).
    None when the legs carry no prices."""
    num = den = 0.0
    for l in legs:
        ep, xp = l.get("entry_price"), l.get("exit_price")
        if not ep or not xp:
            return None
        w = l.get("risk_amount") or 1.0
        num += w * (1.0 if l["side"] == "long" else -1.0) * (xp / ep - 1.0)
        den += w
    return num / den if den else None


def profit_factor(pnls):
    p = np.asarray(pnls, dtype=float)
    gp, gl = p[p > 0].sum(), -p[p < 0].sum()
    if gl > 0:
        return float(gp / gl)
    return float("inf") if gp > 0 else 0.0


def win_rate(pnls):
    p = np.asarray(pnls, dtype=float)
    return float((p > 0).mean()) if len(p) else 0.0


def expectancy(values):
    v = np.asarray(values, dtype=float)
    return float(v.mean()) if len(v) else 0.0


def r_multiples(positions):
    return np.array([p["pnl"] / p["risk_amount"] for p in positions if p["risk_amount"] > 0], dtype=float)


def t_stat(values):
    v = np.asarray(values, dtype=float)
    if len(v) < 3:
        return None
    sd = v.std(ddof=1)
    return float(v.mean() / (sd / math.sqrt(len(v)))) if sd > 0 else None


def max_drawdown(pnls_in_time_order):
    p = np.asarray(pnls_in_time_order, dtype=float)
    if not len(p):
        return 0.0
    eq = np.cumsum(p)
    return float((np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:] - eq).max())
