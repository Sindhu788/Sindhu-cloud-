"""Backtest cost model (Step 15). Conservative and explicit; every assumption is a named constant.

Per side (entry and exit):
- commission: 0.10 % (Binance spot standard TAKER fee; strategies enter and exit at market). A maker option exists but is NOT used by default.
- spread: by liquidity tier of the coin (rank in the universe by 30-day volume): rank <= 5: 0.01 %, <= 20: 0.02 %, else 0.05 %.
- slippage: tier part (rank <= 5: 0.02 %, <= 20: 0.04 %, else 0.08 %) + 0.10 x the coin's median 1-minute range (high/low - 1), i.e. fast and thin
  markets cost more.
- funding: none, because the instruments are SPOT (no perpetual funding, no borrow cost; shorts are modelled as if borrowing were free: a known
  optimistic simplification, listed in docs/BACKTEST_PROTOCOL.md).
Sensitivity: every cost component is multiplied by 1.0, 1.5 or 2.0.

The backtest engine takes commission_pct / slippage_pct / spread_pct as run settings (percent). Because trade records carry the cost components
(commission_cost, slippage_cost, spread_cost), the x1.5 and x2 results are re-priced EXACTLY from the x1 run (the trade path does not depend on costs):
net(m) = pnl + (1 - m) * (commission + slippage + spread) - see reprice().
Paper engine (paper_trading/position_manager.py): commission 0.1 % per side, slippage a constant 0.05 % per side, spread constant _SPREAD_PCT.
Remaining differences: the backtest slippage varies by coin and volatility while paper uses one constant; both ignore partial fills and market impact.
"""
import numpy as np

COMMISSION_TAKER_PCT = 0.10
COMMISSION_MAKER_PCT = 0.10          # no BNB/VIP discount assumed, so maker = taker (conservative)
TIERS = ((5, 0.01, 0.02), (20, 0.02, 0.04), (10 ** 9, 0.05, 0.08))      # (max rank, spread %, slippage tier %)
RANGE_FACTOR = 0.10
SENSITIVITY = (1.0, 1.5, 2.0)


def settings_for(rank, median_range_pct, multiplier=1.0, maker=False):
    spread, slip_tier = next((sp, sl) for mx, sp, sl in TIERS if rank <= mx)
    return {
        "commission_pct": (COMMISSION_MAKER_PCT if maker else COMMISSION_TAKER_PCT) * multiplier,
        "spread_pct": spread * multiplier,
        "slippage_pct": (slip_tier + RANGE_FACTOR * median_range_pct) * multiplier,
    }


def median_range_pct_1m(high, low):
    r = (np.asarray(high) / np.asarray(low) - 1.0) * 100.0
    r = r[np.isfinite(r)]
    return float(np.median(r)) if len(r) else 0.0


def reprice(trades, multiplier):
    """Net P&L per trade if every cost component were `multiplier` times the cost of the run the trades came from (that run is x1).
    In the engine slippage and spread are baked into the fill prices (so already inside `pnl`) and commission is deducted from `pnl`;
    therefore pnl(m) = pnl(1) + (1 - m) * (commission + slippage + spread); m = 0 gives the frictionless gross result."""
    out = []
    for t in trades:
        cost = (t.get("commission_cost") or 0.0) + (t.get("slippage_cost") or 0.0) + (t.get("spread_cost") or 0.0)
        out.append(t["pnl"] + (1.0 - multiplier) * cost)
    return out
