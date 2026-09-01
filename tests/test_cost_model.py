"""cost_model.py: a standalone pre-check comparing a strategy's chosen
stop-loss buffer against the platform's REAL round-trip transaction cost
(commission_pct=0.1, slippage_pct=0.05, mirroring sindhu_web/api/
backtesting.py's RunRequest defaults), so a buffer that's too tight (like
CRT 2.0's original 0.15%) gets flagged before a strategy is ever saved."""

from backtest_engine.cost_model import real_round_trip_cost_pct, check_buffer_safety


def test_real_round_trip_cost_matches_platform_defaults():
    # 2 * (commission 0.1% + slippage 0.05%) = 0.30%
    assert real_round_trip_cost_pct() == 0.30


def test_unsafe_buffer_warns_reproducing_the_crt2_bug_case():
    result = check_buffer_safety(0.15)
    assert result["is_safe"] is False
    assert result["round_trip_cost_pct"] == 0.30
    assert result["required_min_pct"] == 0.60
    assert result["warning"] is not None
    assert "0.15%" in result["warning"]


def test_safe_buffer_stays_silent():
    result = check_buffer_safety(1.0)
    assert result["is_safe"] is True
    assert result["warning"] is None


def test_buffer_exactly_at_the_boundary_is_safe():
    # exactly 2x round-trip cost should pass (>=, not strictly >)
    result = check_buffer_safety(0.60)
    assert result["is_safe"] is True
    assert result["warning"] is None


def test_custom_min_multiple_and_costs_are_honored():
    result = check_buffer_safety(1.0, min_multiple=3.0, commission_pct=0.2, slippage_pct=0.1)
    # round trip = 2*(0.2+0.1) = 0.6, required = 3*0.6 = 1.8
    assert result["round_trip_cost_pct"] == 0.6
    assert result["required_min_pct"] == 1.8
    assert result["is_safe"] is False
