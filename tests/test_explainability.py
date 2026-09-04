"""Master Task 3, Phase 1.12: self_learning_engine/explainability.py."""

from self_learning_engine import explainability


def test_report_narrative_includes_both_periods_and_final_decision():
    gate_result = {
        "passed": True, "reasons": [],
        "discovery_metrics": {"total_trades": 40, "win_rate": 62.0, "profit_factor": 1.4},
        "validation_metrics": {"total_trades": 35, "win_rate": 58.0, "profit_factor": 1.2},
        "win_rate_benchmark_pct": 55.0, "profitable_strategy_count_for_benchmark": 3,
    }
    report = explainability.build_report(
        ["liquidity", "volume"], ["order_block", "poc"], {"ai_used": True, "reason": "diversifies coin exposure"},
        gate_result, "accepted", strategy_id="abc123",
    )
    assert "order_block" in report["narrative"]
    assert "62.0% win rate" in report["narrative"]
    assert "58.0% win rate" in report["narrative"]
    assert "PASSED" in report["narrative"]
    assert "ACCEPTED" in report["narrative"]
    assert "abc123" in report["narrative"]


def test_report_for_a_rejection_states_the_reasons():
    gate_result = {
        "passed": False, "reasons": ["validation period profit factor is 0.8 (needs >= 1.0)"],
        "discovery_metrics": {"total_trades": 40, "win_rate": 62.0, "profit_factor": 1.4},
        "validation_metrics": {"total_trades": 35, "win_rate": 40.0, "profit_factor": 0.8},
        "win_rate_benchmark_pct": None, "profitable_strategy_count_for_benchmark": 0,
    }
    report = explainability.build_report(
        ["trend", "momentum"], ["ema", "rsi"], None, gate_result, "rejected",
    )
    assert report["ai_used"] is False
    assert "REJECTED" in report["narrative"]
    assert "profit factor is 0.8" in report["narrative"]


def test_report_when_never_reached_backtesting():
    report = explainability.build_report(
        ["liquidity", "breakout"], ["fvg"], None, None, "rejected",
    )
    assert "Never reached backtesting" in report["narrative"]
    assert "REJECTED" in report["narrative"]
