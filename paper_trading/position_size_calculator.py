"""Position Size Calculator (Grand Feature Expansion, Phase 5 Feature 13):
a standalone, read-only tool wrapping the engine's own existing sizing
logic (backtest_engine.engine._position_size, never re-invented) so a CEO
can answer "given this balance, risk %, and stop distance, what size would
this actually open at" WITHOUT running a real trade. Confirmed this sizing
logic previously existed only inline inside the engine's own trade-
approval path -- no independently-callable tool existed. Pure calculation,
never touches a real position or the trading engine."""

from backtest_engine.engine import _position_size


def calculate(balance, entry_price, stop_loss, risk_pct, take_profit=None, leverage=1.0):
    """Mirrors exactly how risk_manager.evaluate() sizes a REAL live/paper
    trade: risk_base and available_balance are the same value (the real
    current balance), since live trading (unlike a backtest's fixed-
    capital replay) correctly compounds off current equity."""
    risk_pct_fraction = risk_pct / 100.0
    size = _position_size(balance, balance, entry_price, stop_loss, risk_pct_fraction, 0.1, leverage)
    risk_amount = abs(entry_price - stop_loss) * size if stop_loss is not None else None
    reward_amount = abs(take_profit - entry_price) * size if take_profit is not None else None
    risk_reward_ratio = (reward_amount / risk_amount) if (risk_amount and reward_amount) else None
    return {
        "size": round(size, 8),
        "notional": round(entry_price * size, 2),
        "risk_amount": round(risk_amount, 2) if risk_amount is not None else None,
        "reward_amount": round(reward_amount, 2) if reward_amount is not None else None,
        "risk_reward_ratio": round(risk_reward_ratio, 3) if risk_reward_ratio is not None else None,
    }
