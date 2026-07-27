"""Risk Manager: the one gate that must always approve before a trade
executes, regardless of which path (Strategy or Lesson) produced the
signal. Confidence never factors into this decision -- only account
state and the CEO's configured risk limits.
"""

from backtest_engine.engine import _position_size
from data_engine import storage
from data_engine.logging_setup import log as _log
from paper_trading import dynamic_risk


def account_balance(book_key, initial_balance):
    """(initial_balance * this strategy's Capital Allocation multiplier) +
    this book's realized pnl, read from the O(1) running total in
    paper_account_state (kept in sync by storage.close_paper_position())
    instead of scanning every closed position on every call. The
    multiplier (paper_trading.capital_allocation, default 1.0 = unchanged)
    is the ONLY thing that makes strategies' allocations diverge -- every
    strategy still starts from the same configured initial_balance base."""
    multiplier, _ = storage.get_strategy_capital_multiplier(book_key)
    return initial_balance * multiplier + storage.get_paper_realized_pnl_total(book_key)


def evaluate(book_key, symbol, candidate, settings, exchange=None):
    """Returns (approved: bool, reason: str|None, size: float|None, risk_amount: float|None).

    The open-position cap is per book (per strategy, or the shared
    "__lessons__" book), not shared across strategies -- each strategy is
    independently limited to max_open_trades DISTINCT coins actively
    traded at once, so one strategy filling its coin quota never blocks
    another strategy from opening its own positions."""
    open_symbols = storage.get_open_paper_position_symbols(book_key)
    max_coins = settings.get("max_open_trades", 5)
    if symbol not in open_symbols and len(open_symbols) >= max_coins:
        return False, f"max coins for this strategy reached ({max_coins})", None, None

    if candidate["stop_loss"] is None:
        return False, "no stop-loss could be computed -- risk cannot be sized", None, None

    balance = account_balance(book_key, settings.get("initial_balance", 10000.0))
    if balance <= 0:
        return False, "account balance depleted", None, None

    risk_pct_default = settings.get("risk_pct_default", 1.0)
    if exchange:
        adjusted_pct, note = dynamic_risk.compute_risk_pct(exchange, symbol, risk_pct_default)
        if note:
            _log(f"[paper-trading] Dynamic Risk Sizing: {note}")
    else:
        adjusted_pct = risk_pct_default
    risk_pct = adjusted_pct / 100.0
    # Live/paper trading risks a % of the real current balance (both
    # arguments are the same value here) -- unlike a backtest's single-pass
    # replay of thousands of historical bars, trades here happen slowly in
    # real time, so compounding off current equity is the correct, standard
    # behavior for an actual account, not the runaway-growth bug that
    # affected backtesting.
    size = _position_size(balance, balance, candidate["entry_price"], candidate["stop_loss"], risk_pct, 0.1)
    if size <= 0:
        return False, "computed position size is zero", None, None

    risk_amount = abs(candidate["entry_price"] - candidate["stop_loss"]) * size
    return True, None, size, risk_amount
