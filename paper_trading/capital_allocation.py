"""Capital Allocation Engine (Additional Features, B2): instead of every
strategy getting an equal, fixed virtual balance, allocates a bounded
multiplier of the base initial_balance from each strategy's own Sharpe
Ratio (paper_trading.insights.compute_risk_metrics, already verified) --
no new performance metric invented here, purely an allocation decision on
top of an existing one.

Documented formula (simple, linear, bounded -- transparent, not a hidden
model): multiplier = clamp(1.0 + sharpe_ratio * SHARPE_SENSITIVITY, MIN_MULTIPLIER, MAX_MULTIPLIER)

  - A Sharpe of 0 keeps the multiplier at exactly 1.0 (the historical
    equal-allocation baseline).
  - SHARPE_SENSITIVITY = 0.1 means a Sharpe of +2.0 pushes the multiplier
    to 1.2 (20% more capital); a Sharpe of -2.0 pushes it to 0.8.
  - Hard bounds MIN_MULTIPLIER=0.5 / MAX_MULTIPLIER=1.5 cap the swing at
    +/-50% regardless of how extreme a Sharpe reading gets -- "safe
    bounds" per the spec, not proportional-forever scaling.
  - A strategy with too little trade history for a real Sharpe (see
    compute_risk_metrics's own sample-size gate) keeps multiplier=1.0,
    unchanged -- never penalized or rewarded for lacking data.

This ONLY affects account_balance() (risk_manager.py) -- the number used
to size positions and compute displayed balance. It never touches the
backtest engine, PnL calculation, or trade execution.
"""

from datetime import datetime, timezone

from data_engine import storage
from backtest_engine import strategy_library as lib
from paper_trading import insights

SHARPE_SENSITIVITY = 0.1
MIN_MULTIPLIER = 0.5
MAX_MULTIPLIER = 1.5


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def compute_multiplier(sharpe_ratio):
    if sharpe_ratio is None:
        return 1.0
    raw = 1.0 + sharpe_ratio * SHARPE_SENSITIVITY
    return round(max(MIN_MULTIPLIER, min(MAX_MULTIPLIER, raw)), 3)


def recompute_all_allocations():
    """Called periodically (see engine.py's tick loop) -- recomputes every
    strategy's multiplier from its current Sharpe Ratio. Cheap: reuses
    already-computed per-strategy risk metrics, no new DB scans beyond
    what insights.compute_risk_metrics already does."""
    since = insights.fresh_session_start()
    now = _now_iso()
    updated = []
    for meta in lib.list_all():
        sid = meta["id"]
        metrics = insights.compute_risk_metrics(sid, since=since)
        if metrics["sample_size"] < 5:
            continue  # too little data -- leave at the default 1.0, don't guess
        multiplier = compute_multiplier(metrics["sharpe_ratio"])
        if multiplier == 1.0:
            reason = "Sharpe Ratio near zero -- standard allocation."
        elif multiplier > 1.0:
            reason = f"Sharpe Ratio {metrics['sharpe_ratio']:.2f} (strong track record) -- allocated {multiplier}x base capital."
        else:
            reason = f"Sharpe Ratio {metrics['sharpe_ratio']:.2f} (weak track record) -- allocation reduced to {multiplier}x base capital."
        storage.set_strategy_capital_multiplier(sid, multiplier, reason, now)
        updated.append({"strategy_id": sid, "multiplier": multiplier, "reason": reason})
    return updated
