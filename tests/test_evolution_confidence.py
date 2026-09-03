"""Grand Feature Expansion, Phase 6 Feature 10: Evolution Confidence Score
(evolution_engine/evolution_confidence.py) -- how much to trust ONE
finalized evolution comparison, genuinely distinct from paper_trading/
confidence.py (per-trade) and pattern_stats.py (per-pattern statistical
classification). A plain, documented weighted sum, same convention as
insights.compute_strategy_health_score.
"""

import pytest

from evolution_engine import evolution_confidence


def _comparison(before=None, after=None):
    return {"before": before, "after": after}


def test_pending_comparison_has_no_confidence_score():
    result = evolution_confidence.compute_confidence(_comparison(before={"win_rate": 50.0}, after=None))
    assert result["confidence_score"] is None
    assert result["reason"] is not None


def test_full_sample_and_all_metrics_comparable_and_big_swing_scores_high():
    before = {"win_rate": 40.0, "total_pnl": 100.0, "avg_profit_factor": 1.0, "max_drawdown_pct": 20.0}
    after = {"trades": 100, "win_rate": 70.0, "total_pnl": 300.0, "avg_profit_factor": 2.0, "max_drawdown_pct": 5.0}
    result = evolution_confidence.compute_confidence(_comparison(before, after))
    assert result["confidence_score"] is not None
    assert result["confidence_score"] > 70
    assert result["components"]["comparable_metrics"] == 4


def test_low_sample_size_reduces_the_score():
    before = {"win_rate": 40.0, "total_pnl": 100.0, "avg_profit_factor": 1.0, "max_drawdown_pct": 20.0}
    after_full = {"trades": 100, "win_rate": 70.0, "total_pnl": 300.0, "avg_profit_factor": 2.0, "max_drawdown_pct": 5.0}
    after_thin = {**after_full, "trades": 10}
    full = evolution_confidence.compute_confidence(_comparison(before, after_full))
    thin = evolution_confidence.compute_confidence(_comparison(before, after_thin))
    assert thin["confidence_score"] < full["confidence_score"]
    assert thin["components"]["sample_size_score"] < full["components"]["sample_size_score"]


def test_a_barely_there_swing_scores_lower_than_a_decisive_one():
    before = {"win_rate": 50.0, "total_pnl": 100.0, "avg_profit_factor": 1.5, "max_drawdown_pct": 10.0}
    after_barely = {"trades": 100, "win_rate": 50.1, "total_pnl": 100.1, "avg_profit_factor": 1.5, "max_drawdown_pct": 10.0}
    after_decisive = {"trades": 100, "win_rate": 80.0, "total_pnl": 500.0, "avg_profit_factor": 3.0, "max_drawdown_pct": 2.0}
    barely = evolution_confidence.compute_confidence(_comparison(before, after_barely))
    decisive = evolution_confidence.compute_confidence(_comparison(before, after_decisive))
    assert barely["confidence_score"] < decisive["confidence_score"]


def test_missing_metrics_reduce_coverage_score():
    before = {"win_rate": 40.0, "total_pnl": 100.0}  # only 2 of 4 metrics present
    after = {"trades": 100, "win_rate": 70.0, "total_pnl": 300.0}
    result = evolution_confidence.compute_confidence(_comparison(before, after))
    assert result["components"]["comparable_metrics"] == 2
    assert result["components"]["coverage_score"] == pytest.approx(10.0)  # half of 20


def test_score_never_exceeds_100():
    before = {"win_rate": 1.0, "total_pnl": 1.0, "avg_profit_factor": 1.0, "max_drawdown_pct": 50.0}
    after = {"trades": 100000, "win_rate": 99.0, "total_pnl": 100000.0, "avg_profit_factor": 100.0, "max_drawdown_pct": 0.1}
    result = evolution_confidence.compute_confidence(_comparison(before, after))
    assert result["confidence_score"] <= 100.0


def test_endpoint_attaches_confidence_to_each_comparison(test_db):
    from evolution_engine import generation_manager
    from data_engine import storage
    from sindhu_web.api.evolution import evolution_comparisons

    base_id = generation_manager.create_new_strategy_lineage(
        "Parent", {"risk_reward": 2.0}, ["trend"], "sindhu_deterministic", False, "seed", "2026-01-01T00:00:00+00:00",
    )
    child_id = generation_manager.create_new_strategy_lineage(
        "Child", {"risk_reward": 2.0}, ["trend"], "sindhu_deterministic", False, "mutation", "2026-01-01T00:00:00+00:00", base_id=base_id,
    )
    comp_id = storage.create_evolution_comparison(base_id, base_id, child_id, 100, {"win_rate": 40.0}, "2026-01-01T00:00:00+00:00")
    storage.finalize_evolution_comparison(comp_id, {"win_rate": 70.0, "trades": 100}, "improved", False, "2026-01-01T00:00:00+00:00")

    result = evolution_comparisons()
    assert len(result["comparisons"]) == 1
    assert "confidence" in result["comparisons"][0]
    assert result["comparisons"][0]["confidence"]["confidence_score"] is not None
