"""Risk Manager: the one gate that must always approve before a trade
executes, regardless of which path (Strategy or Lesson) produced the
signal. Confidence never factors into this decision -- only account
state and the CEO's configured risk limits.
"""

from backtest_engine.engine import _position_size
from data_engine import storage


def account_balance(initial_balance):
    """initial_balance + every closed paper trade's realized pnl -- there's
    no separate "account" table, the ledger is the trade history itself."""
    balance = initial_balance
    for pos in storage.list_closed_paper_positions(limit=100000):
        if pos.get("pnl") is not None:
            balance += pos["pnl"]
    return balance


def evaluate(candidate, settings):
    """Returns (approved: bool, reason: str|None, size: float|None, risk_amount: float|None)."""
    open_positions = storage.get_open_paper_positions()
    max_open = settings.get("max_open_trades", 5)
    if len(open_positions) >= max_open:
        return False, f"max open trades reached ({max_open})", None, None

    if candidate["stop_loss"] is None:
        return False, "no stop-loss could be computed -- risk cannot be sized", None, None

    balance = account_balance(settings.get("initial_balance", 10000.0))
    if balance <= 0:
        return False, "account balance depleted", None, None

    risk_pct = settings.get("risk_pct_default", 1.0) / 100.0
    size = _position_size(balance, candidate["entry_price"], candidate["stop_loss"], risk_pct, 0.1)
    if size <= 0:
        return False, "computed position size is zero", None, None

    risk_amount = abs(candidate["entry_price"] - candidate["stop_loss"]) * size
    return True, None, size, risk_amount
