"""Investigation Batch 2026-09-17, item 1.2: real evidence showed 14
different strategies each independently opened one position on the same
coin (UUSDT) while staying comfortably under the existing dollar-based
max_portfolio_risk_pct_per_coin cap (see test_portfolio_exposure_control.py
for that cap's own coverage) -- a $-at-stop cap alone never limits raw
position COUNT when each individual risk is small. risk_manager.evaluate()
now ALSO rejects a new entry once max_open_positions_per_coin positions are
already open on the same coin across every strategy combined.
"""

from data_engine import storage
from paper_trading import position_manager, risk_manager

EXCHANGE = "binance"
SETTINGS = {
    "max_open_trades": 20, "initial_balance": 100.0, "risk_pct_default": 0.5,
    "max_portfolio_risk_pct_per_coin": 0,  # isolate the count cap from the $ cap
    "max_open_positions_per_coin": 5,
}


def _candidate(strategy_id, symbol, entry, sl, tp):
    return {
        "direction": "bullish", "entry_price": entry, "stop_loss": sl, "take_profit": tp,
        "entry_reason": "test", "strategy_id": strategy_id, "strategy_name": strategy_id,
        "strategy_version": "v1", "lesson_ids": [], "timeframe": "1h", "stop_loss_type": "structure",
    }


def _open(strategy_id, symbol, entry, sl, tp, settings=SETTINGS, exchange=EXCHANGE):
    cand = _candidate(strategy_id, symbol, entry, sl, tp)
    approved, reason, size, risk_amount = risk_manager.evaluate(strategy_id, symbol, cand, settings, exchange=exchange)
    if not approved:
        return approved, reason, None
    pos = position_manager.open_position(exchange, symbol, cand, size, risk_amount, confidence=0.9,
                                          market_snapshot={"market_state": "trending_up", "session": "london"})
    return approved, reason, pos


def test_up_to_the_cap_is_approved_across_different_strategies(test_db):
    for i in range(5):
        approved, reason, pos = _open(f"strat{i}", "UUSDT", 1.0, 0.98, 1.06)
        assert approved is True, reason
    open_positions = storage.get_open_paper_positions(exchange=EXCHANGE, symbol="UUSDT")
    assert len(open_positions) == 5


def test_the_6th_strategy_on_the_same_coin_is_rejected(test_db):
    for i in range(5):
        _open(f"strat{i}", "UUSDT", 1.0, 0.98, 1.06)
    approved, reason, pos = _open("strat5", "UUSDT", 1.0, 0.98, 1.06)
    assert approved is False
    assert "max positions per coin" in reason
    assert "UUSDT" in reason
    assert pos is None


def test_a_different_coin_is_unaffected(test_db):
    for i in range(5):
        _open(f"strat{i}", "UUSDT", 1.0, 0.98, 1.06)
    approved, reason, pos = _open("stratETH", "ETHUSDT", 2000.0, 1980.0, 2080.0)
    assert approved is True, reason


def test_zero_disables_the_check(test_db):
    disabled = {**SETTINGS, "max_open_positions_per_coin": 0}
    for i in range(14):
        approved, reason, pos = _open(f"strat{i}", "UUSDT", 1.0, 0.98, 1.06, settings=disabled)
        assert approved is True, reason
    assert len(storage.get_open_paper_positions(exchange=EXCHANGE, symbol="UUSDT")) == 14


def test_no_exchange_passed_skips_the_check(test_db):
    """Backward compatibility, same convention the dollar cap already
    documents for itself: an older caller that never passes exchange=
    behaves exactly as before this feature existed."""
    for i in range(10):
        cand = _candidate(f"strat{i}", "UUSDT", 1.0, 0.98, 1.06)
        approved, reason, size, risk_amount = risk_manager.evaluate(f"strat{i}", "UUSDT", cand, SETTINGS)
        assert approved is True, reason
