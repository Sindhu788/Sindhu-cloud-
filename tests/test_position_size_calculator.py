"""Grand Feature Expansion, Phase 5 Feature 13: Position Size Calculator
(paper_trading/position_size_calculator.py) -- a standalone, read-only
wrapper around the engine's own existing sizing logic
(backtest_engine.engine._position_size, never re-invented). Pure
calculation; never touches a real position or the trading engine.
"""

import pytest

from paper_trading import position_size_calculator


def test_basic_risk_based_sizing():
    # $10,000 balance, 1% risk = $100 risk budget. Entry 100, stop 95 ->
    # $5 stop distance -> size = 100 / 5 = 20 units.
    result = position_size_calculator.calculate(10000.0, 100.0, 95.0, risk_pct=1.0)
    assert result["size"] == pytest.approx(20.0)
    assert result["risk_amount"] == pytest.approx(100.0)
    assert result["notional"] == pytest.approx(2000.0)


def test_take_profit_computes_reward_and_risk_reward_ratio():
    result = position_size_calculator.calculate(10000.0, 100.0, 95.0, risk_pct=1.0, take_profit=110.0)
    assert result["reward_amount"] == pytest.approx(200.0)
    assert result["risk_reward_ratio"] == pytest.approx(2.0)


def test_no_stop_loss_means_no_risk_amount():
    result = position_size_calculator.calculate(10000.0, 100.0, None, risk_pct=1.0)
    assert result["risk_amount"] is None
    assert result["size"] > 0  # falls back to the fixed-fraction sizing path


def test_zero_balance_yields_zero_size():
    result = position_size_calculator.calculate(0.0, 100.0, 95.0, risk_pct=1.0)
    assert result["size"] == 0.0


def test_leverage_raises_the_size_cap():
    # A large risk % would normally be capped by available balance / entry
    # price -- leverage raises that cap.
    no_leverage = position_size_calculator.calculate(1000.0, 100.0, 99.0, risk_pct=50.0, leverage=1.0)
    with_leverage = position_size_calculator.calculate(1000.0, 100.0, 99.0, risk_pct=50.0, leverage=3.0)
    assert with_leverage["size"] > no_leverage["size"]


def test_endpoint_calculates(test_db):
    from sindhu_web.api.paper_trading import PositionSizeCalculatorRequest, calculate_position_size

    result = calculate_position_size(PositionSizeCalculatorRequest(
        balance=10000.0, entry_price=100.0, stop_loss=95.0, risk_pct=1.0))
    assert result["size"] == pytest.approx(20.0)


def test_endpoint_rejects_zero_entry_price(test_db):
    from fastapi import HTTPException
    from sindhu_web.api.paper_trading import PositionSizeCalculatorRequest, calculate_position_size

    with pytest.raises(HTTPException):
        calculate_position_size(PositionSizeCalculatorRequest(balance=10000.0, entry_price=0.0, risk_pct=1.0))
