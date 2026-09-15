"""Grand Master Batch #2, Phase 3.3: real evidence for Portfolio-Level
Exposure Control -- risk_manager.evaluate() now rejects a NEW entry once a
single coin's combined risk across EVERY strategy (not just the one book
being evaluated) would exceed max_portfolio_risk_pct_per_coin of
initial_balance. Reuses paper_trading.portfolio.compute_coin_exposure(),
previously informational-only.
"""

import pytest

from data_engine import storage
from paper_trading import position_manager, risk_manager

EXCHANGE = "binance"
SETTINGS = {
    "max_open_trades": 5, "initial_balance": 10000.0, "risk_pct_default": 1.0,
    "max_portfolio_risk_pct_per_coin": 10.0,  # $1000 cap on BTCUSDT combined risk
}


def _candidate(strategy_id, symbol, entry, sl, tp):
    return {
        "direction": "bullish", "entry_price": entry, "stop_loss": sl, "take_profit": tp,
        "entry_reason": "test", "strategy_id": strategy_id, "strategy_name": strategy_id,
        "strategy_version": "v1", "lesson_ids": [], "timeframe": "1h", "stop_loss_type": "structure",
    }


def _open(strategy_id, symbol, entry, sl, tp, settings=SETTINGS):
    cand = _candidate(strategy_id, symbol, entry, sl, tp)
    approved, reason, size, risk_amount = risk_manager.evaluate(strategy_id, symbol, cand, settings, exchange=EXCHANGE)
    if not approved:
        return approved, reason, None
    pos = position_manager.open_position(EXCHANGE, symbol, cand, size, risk_amount, confidence=0.9,
                                          market_snapshot={"market_state": "trending_up", "session": "london"})
    return approved, reason, pos


def test_first_strategy_on_a_coin_is_approved_normally(test_db):
    # A single strategy risking 1% of $10k ($100) is nowhere near the $1000 cap.
    approved, reason, pos = _open("stratA", "BTCUSDT", 100.0, 99.0, 104.0)
    assert approved is True, reason


def test_many_strategies_piling_onto_the_same_coin_eventually_get_rejected(test_db):
    # Each strategy risks ~$100 (1% of $10k). The 10th+ would push combined
    # risk on BTCUSDT past the $1000 cap (10% of $10k).
    approvals = []
    for i in range(15):
        approved, reason, pos = _open(f"strat{i}", "BTCUSDT", 100.0, 99.0, 104.0)
        approvals.append(approved)
    assert any(approvals), "at least the early ones should be approved"
    assert not all(approvals), "eventually the combined-risk cap must reject further entries on the same coin"
    assert approvals[0] is True


def test_rejection_reason_names_the_real_cap_and_current_exposure(test_db):
    for i in range(12):
        _open(f"strat{i}", "BTCUSDT", 100.0, 99.0, 104.0)
    approved, reason, pos = _open("strat_overflow", "BTCUSDT", 100.0, 99.0, 104.0)
    assert approved is False
    assert "portfolio-wide risk cap" in reason
    assert "$1000.00" in reason or "1000.00" in reason


def test_a_different_coin_is_unaffected_by_another_coins_saturation(test_db):
    for i in range(12):
        _open(f"strat{i}", "BTCUSDT", 100.0, 99.0, 104.0)
    approved, reason, pos = _open("stratETH", "ETHUSDT", 2000.0, 1980.0, 2080.0)
    assert approved is True, reason


def test_setting_the_cap_to_zero_disables_the_check(test_db):
    disabled_settings = {**SETTINGS, "max_portfolio_risk_pct_per_coin": 0}
    for i in range(20):
        approved, reason, pos = _open(f"strat{i}", "BTCUSDT", 100.0, 99.0, 104.0, settings=disabled_settings)
        assert approved is True, reason


def test_no_exchange_passed_skips_the_check_same_as_before_this_feature(test_db):
    """Backward compatibility: an existing caller that never passed
    exchange= (like this suite's older test_multi_strategy_independence.py
    helper) must behave exactly as it did before this feature existed."""
    for i in range(20):
        cand = _candidate(f"strat{i}", "BTCUSDT", 100.0, 99.0, 104.0)
        approved, reason, size, risk_amount = risk_manager.evaluate(f"strat{i}", "BTCUSDT", cand, SETTINGS)
        assert approved is True, reason
