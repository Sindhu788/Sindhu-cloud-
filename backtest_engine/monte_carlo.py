"""Monte Carlo Engine, basic version (Deeper Verification & Robustness
Group, item 4): reshuffles the ORDER of a completed backtest's own real
trades (never invents new trades, never touches the backtest engine or
recomputes PnL) many times, and reports the distribution of final-equity
outcomes. A backtest result that only looks good because of the specific
order a handful of big winners happened to land in will show a wide,
worrying spread here; a genuinely robust edge stays profitable across
most reshuffled orders too.

Important correctness note found while testing this feature: naively
summing raw PnL dollars, or even compounding percentage returns with plain
multiplication, is mathematically ORDER-INVARIANT -- addition and
multiplication are both commutative, so reshuffling either one always
produces the exact same final number no matter the order, which would make
this whole feature a no-op that always reports p5 == median == p95. Order
only genuinely matters once something NON-linear/path-dependent is in the
loop -- here, a max-drawdown "risk of ruin" stop: if running equity ever
falls more than RUIN_DRAWDOWN_PCT below its peak-so-far, that simulated
run stops taking further trades (as a real trader/the system's own
Drawdown Protection Engine would). Since large losses landing early (on a
smaller cushion) trigger this far more easily than the same losses landing
late (after gains have built a buffer), the stop makes the final result
genuinely depend on the shuffled order -- which is the entire point of
running this simulation."""

import random

from data_engine import storage

DEFAULT_ITERATIONS = 1000
_MIN_TRADES = 10
RUIN_DRAWDOWN_PCT = 50.0  # matches a realistic "the strategy would be abandoned" bar


def run_monte_carlo(batch_id, iterations=DEFAULT_ITERATIONS, initial_balance=10000.0, seed=None):
    """Returns {"available": False, "reason": ...} if the batch doesn't have
    enough closed trades to make reshuffling meaningful (degrades
    gracefully rather than a misleading result from 2-3 trades)."""
    trades = storage.get_trades(batch_id)
    pnl_pcts = [t["pnl_pct"] for t in trades if t["pnl_pct"] is not None]
    if len(pnl_pcts) < _MIN_TRADES:
        return {"available": False, "reason": f"only {len(pnl_pcts)} closed trades (need at least {_MIN_TRADES})"}

    def _run_sequence(sequence):
        """Compounds each trade onto the running balance, but stops early
        (freezing the balance) if drawdown-from-peak exceeds
        RUIN_DRAWDOWN_PCT -- see module docstring for why this is the part
        that makes order actually matter."""
        balance = initial_balance
        peak = initial_balance
        ruined = False
        for pct in sequence:
            balance *= (1 + pct / 100)
            balance = max(balance, 0.0)
            peak = max(peak, balance)
            if peak > 0 and (peak - balance) / peak * 100 >= RUIN_DRAWDOWN_PCT:
                ruined = True
                break
        return balance, ruined

    rng = random.Random(seed)  # seed=None -> real randomness; a fixed seed is only for tests
    finals, ruin_count = [], 0
    for _ in range(iterations):
        shuffled = pnl_pcts[:]
        rng.shuffle(shuffled)
        final_balance, ruined = _run_sequence(shuffled)
        finals.append(final_balance)
        if ruined:
            ruin_count += 1
    finals.sort()

    def percentile(p):
        idx = int(round(p / 100 * (len(finals) - 1)))
        return round(finals[idx], 2)

    original_final, _ = _run_sequence(pnl_pcts)  # the trades' actual recorded order, same rule applied
    original_final = round(original_final, 2)
    p5, p50, p95 = percentile(5), percentile(50), percentile(95)

    # Plain-language robustness read: how much of the simulated outcomes
    # ended up profitable at all, and how far the worst-case (5th
    # percentile) result sits below the original reported result.
    profitable_share_pct = round(sum(1 for f in finals if f > initial_balance) / len(finals) * 100, 1)
    downside_vs_original_pct = round((original_final - p5) / initial_balance * 100, 2) if initial_balance else None
    risk_of_ruin_pct = round(ruin_count / iterations * 100, 1)

    return {
        "available": True,
        "batch_id": batch_id,
        "trade_count": len(pnl_pcts),
        "iterations": iterations,
        "initial_balance": initial_balance,
        "original_final_equity": original_final,
        "p5_final_equity": p5,
        "median_final_equity": p50,
        "p95_final_equity": p95,
        "worst_final_equity": round(finals[0], 2),
        "best_final_equity": round(finals[-1], 2),
        "profitable_outcomes_pct": profitable_share_pct,
        "downside_vs_original_pct": downside_vs_original_pct,
        "risk_of_ruin_pct": risk_of_ruin_pct,
        "ruin_definition": f"equity fell {RUIN_DRAWDOWN_PCT:.0f}%+ below its peak at some point in the reshuffled order",
    }
