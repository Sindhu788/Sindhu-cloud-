"""Grand Master Batch, Phase 4 Item 3: Practice Mode -- lets the CEO
manually enter a hypothetical trade (strategy, coin, direction, entry/
stop/target) and see exactly how the system would evaluate its
confidence and size it, for learning purposes only. Never opens a real
or paper position -- reuses the exact same real confidence-scoring
(paper_trading.confidence.score) and position-sizing
(paper_trading.position_size_calculator, itself already a read-only
what-if tool) logic every real trade goes through, just fed a
CEO-typed hypothetical instead of a real generated signal.
"""

from backtest_engine import strategy_library
from paper_trading import confidence as confidence_mod
from paper_trading import config as pt_config
from paper_trading import position_size_calculator


def evaluate(strategy_id, symbol, direction, entry_price, stop_loss, take_profit=None,
             market_state="ranging", session="unknown"):
    """direction: "bullish" or "bearish" (confidence.score's own
    vocabulary). Returns confidence (0-100, the exact real scoring logic)
    plus the exact real position-sizing math against the CEO's currently
    configured balance/risk %. Raises ValueError for an unknown
    strategy_id -- practice mode should reflect a REAL strategy's real
    track record, never a guessed one."""
    meta = next((m for m in strategy_library.list_all() if m["id"] == strategy_id), None)
    if not meta:
        raise ValueError(f"unknown strategy_id: {strategy_id}")

    candidate = {
        "source": "strategy", "strategy_id": strategy_id,
        "strategy_version": meta.get("current_version"), "direction": direction,
        "lesson_ids": [],
    }
    market_snapshot = {"symbol": symbol, "market_state": market_state, "session": session}
    confidence = confidence_mod.score(candidate, market_snapshot)

    settings = pt_config.load()
    balance = settings.get("initial_balance", 10000.0)
    risk_pct = settings.get("risk_pct_default", 1.0)
    sizing = position_size_calculator.calculate(balance, entry_price, stop_loss, risk_pct, take_profit)

    return {
        "practice_only": True,
        "strategy_id": strategy_id, "strategy_name": meta["name"],
        "confidence": confidence,
        "balance_used": balance, "risk_pct_used": risk_pct,
        "sizing": sizing,
    }
