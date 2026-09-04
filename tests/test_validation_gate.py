"""Master Task 3, Phase 1.6/1.7/1.8: self_learning_engine/validation_gate.py
-- the mandatory out-of-sample gate (PF >= 1.0 in BOTH periods
independently), the 25-trade-per-period minimum (reusing the real Wilson
gate threshold), and the dual 1:2 RR + real-data win-rate benchmark filter.
"""

from datetime import datetime, timezone

import pytest

from data_engine import storage
from self_learning_engine import validation_gate


def _now():
    return datetime.now(timezone.utc).isoformat()


def _make_batch_with_symbols(batch_id, symbol_metrics):
    """symbol_metrics: list of (total_trades, wins, profit_factor, risk_reward)."""
    storage.create_batch(batch_id, "Test Strategy", "binance", {"initial_balance": 1000.0}, _now())
    for i, (total_trades, wins, profit_factor, risk_reward) in enumerate(symbol_metrics):
        storage.save_result(
            batch_id, f"SYM{i}USDT", "5m", "completed",
            {
                "total_trades": total_trades, "wins": wins, "losses": total_trades - wins,
                "final_balance": 1000.0 + 10 * (wins - (total_trades - wins)),
                "profit_factor": profit_factor, "risk_reward": risk_reward,
            },
            _now(),
        )


def test_compute_period_metrics_pools_across_symbols(test_db):
    _make_batch_with_symbols("batchA", [(20, 15, 1.8, 2.1), (20, 10, 1.2, 1.9)])
    m = validation_gate.compute_period_metrics("batchA")
    assert m["total_trades"] == 40
    assert m["win_rate"] == 62.5  # 25/40
    assert m["profit_factor"] == pytest.approx(1.5)  # avg(1.8, 1.2)


def test_compute_period_metrics_none_for_unknown_batch(test_db):
    assert validation_gate.compute_period_metrics("does-not-exist") is None


def test_evaluate_fails_when_discovery_period_has_too_few_trades(test_db):
    discovery = {"total_trades": 10, "win_rate": 80.0, "profit_factor": 2.0}
    validation = {"total_trades": 30, "win_rate": 80.0, "profit_factor": 2.0}
    result = validation_gate.evaluate(discovery, validation, structural_risk_reward=2.0)
    assert result["passed"] is False
    assert any("discovery" in r and "25" in r for r in result["reasons"])


def test_evaluate_fails_when_validation_period_profit_factor_below_1(test_db):
    discovery = {"total_trades": 30, "win_rate": 80.0, "profit_factor": 1.5}
    validation = {"total_trades": 30, "win_rate": 80.0, "profit_factor": 0.8}
    result = validation_gate.evaluate(discovery, validation, structural_risk_reward=2.0)
    assert result["passed"] is False
    assert any("validation" in r and "profit factor" in r for r in result["reasons"])


def test_evaluate_never_blends_periods_reports_both_failures(test_db):
    discovery = {"total_trades": 10, "win_rate": 80.0, "profit_factor": 0.5}
    validation = {"total_trades": 30, "win_rate": 80.0, "profit_factor": 2.0}
    result = validation_gate.evaluate(discovery, validation, structural_risk_reward=2.0)
    assert any("discovery" in r for r in result["reasons"])
    assert not any("validation" in r for r in result["reasons"])  # validation period itself was clean


def test_evaluate_fails_on_structural_risk_reward_below_1_to_2(test_db):
    discovery = {"total_trades": 30, "win_rate": 80.0, "profit_factor": 2.0}
    validation = {"total_trades": 30, "win_rate": 80.0, "profit_factor": 2.0}
    result = validation_gate.evaluate(discovery, validation, structural_risk_reward=1.5)
    assert result["passed"] is False
    assert any("risk:reward" in r for r in result["reasons"])


def test_evaluate_passes_when_everything_clears_and_no_benchmark_yet(test_db):
    # Fewer than 2 profitable strategies exist yet -- benchmark is None,
    # so the win-rate half of the dual filter cannot fail (nothing to
    # compare against), but the mandatory OOS/RR checks all still apply.
    discovery = {"total_trades": 30, "win_rate": 60.0, "profit_factor": 1.3}
    validation = {"total_trades": 30, "win_rate": 55.0, "profit_factor": 1.1}
    result = validation_gate.evaluate(discovery, validation, structural_risk_reward=2.0)
    assert result["passed"] is True
    assert result["win_rate_benchmark_pct"] is None


def _seed_profitable_strategy(strategy_id, closed_count, win_count, pnl_total):
    with storage.get_conn() as conn:
        conn.execute(
            """INSERT INTO paper_account_state (strategy_id, realized_pnl_total, closed_count, win_count, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (strategy_id, pnl_total, closed_count, win_count, _now()),
        )


def test_win_rate_benchmark_uses_the_lowest_real_profitable_win_rate(test_db):
    _seed_profitable_strategy("s1", 30, 20, 100.0)  # 66.7% win rate, profitable
    _seed_profitable_strategy("s2", 40, 22, 50.0)   # 55.0% win rate, profitable
    _seed_profitable_strategy("s3", 30, 5, -200.0)  # losing -- excluded
    _seed_profitable_strategy("s4", 10, 9, 50.0)    # profitable but under 25 trades -- excluded

    benchmark_pct, count = validation_gate.compute_win_rate_benchmark()
    assert count == 2
    assert benchmark_pct == 55.0


def test_evaluate_fails_a_candidate_below_the_real_benchmark(test_db):
    _seed_profitable_strategy("s1", 30, 20, 100.0)  # 66.7%
    _seed_profitable_strategy("s2", 40, 24, 50.0)   # 60.0%

    discovery = {"total_trades": 30, "win_rate": 45.0, "profit_factor": 1.3}
    validation = {"total_trades": 30, "win_rate": 45.0, "profit_factor": 1.1}
    result = validation_gate.evaluate(discovery, validation, structural_risk_reward=2.0)
    assert result["passed"] is False
    assert any("benchmark" in r for r in result["reasons"])
