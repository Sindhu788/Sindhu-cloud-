"""Grand Feature Expansion, Phase 6 Feature 7: Strategy Lineage
Explainability (evolution_engine/lineage_explainer.py) -- synthesizes
already-existing generation history, mutation reasons, and rollback
verdicts into one plain-language narrative. Computes nothing new.
"""

from evolution_engine import generation_manager, lineage_explainer
from data_engine import storage

CONFIG = {"risk_reward": 2.0, "risk_pct": 1.0, "entry_timeframe": "5m"}


def _seed_lineage(base_id, reason="seed", now_iso="2026-01-01T00:00:00+00:00"):
    return generation_manager.create_new_strategy_lineage(
        "Gen1", CONFIG, ["trend"], "sindhu_deterministic", False, reason, now_iso, base_id=base_id,
    )


def test_unknown_lineage_returns_none(test_db):
    assert lineage_explainer.explain_lineage("does-not-exist") is None


def test_single_generation_lineage_has_a_basic_narrative(test_db):
    base_id = "lineage1"
    _seed_lineage(base_id)
    result = lineage_explainer.explain_lineage(base_id)
    assert result["generation_count"] == 1
    assert result["active_generation"] == 1
    assert "Generation 1" in result["narrative"]
    assert "seed" in result["narrative"]


def test_improved_generation_narrative_mentions_kept(test_db):
    base_id = "lineage2"
    _seed_lineage(base_id)
    child_id = generation_manager.create_next_strategy_generation(
        base_id, "Gen2", CONFIG, ["trend"], "sindhu_deterministic", False, "tightened stop-loss", "2026-01-02T00:00:00+00:00",
    )
    comp_id = storage.create_evolution_comparison(base_id, base_id, child_id, 100, {"win_rate": 40.0}, "2026-01-02T00:00:00+00:00")
    storage.finalize_evolution_comparison(comp_id, {"win_rate": 70.0}, "improved", False, "2026-01-02T00:00:00+00:00")

    result = lineage_explainer.explain_lineage(base_id)
    assert result["generation_count"] == 2
    assert "tightened stop-loss" in result["narrative"]
    assert "kept" in result["narrative"].lower()
    assert result["active_generation"] == 2


def test_regressed_generation_narrative_mentions_rollback_and_pinned_generation(test_db):
    base_id = "lineage3"
    parent_id = _seed_lineage(base_id)
    child_id = generation_manager.create_next_strategy_generation(
        base_id, "Gen2", CONFIG, ["trend"], "sindhu_deterministic", False, "widened take-profit", "2026-01-02T00:00:00+00:00",
    )
    comp_id = storage.create_evolution_comparison(base_id, parent_id, child_id, 100, {"win_rate": 60.0}, "2026-01-02T00:00:00+00:00")
    storage.finalize_evolution_comparison(comp_id, {"win_rate": 30.0}, "regressed", True, "2026-01-02T00:00:00+00:00")
    # rollback.try_finalize_comparison() is what actually pins the lineage
    # back on a real regression -- simulated directly here since setting up
    # a real MIN_TRADES_FOR_COMPARISON-sized backtest_summary is out of
    # scope for this narrative-synthesis test.
    storage.set_active_generation_id(base_id, parent_id, "2026-01-02T00:00:00+00:00")

    result = lineage_explainer.explain_lineage(base_id)
    assert "rolled back" in result["narrative"].lower()
    # The lineage is now pinned back to generation 1, not the latest (2).
    assert result["active_generation"] == 1


def test_pending_comparison_narrative_says_still_waiting(test_db):
    base_id = "lineage4"
    _seed_lineage(base_id)
    child_id = generation_manager.create_next_strategy_generation(
        base_id, "Gen2", CONFIG, ["trend"], "sindhu_deterministic", False, "new idea", "2026-01-02T00:00:00+00:00",
    )
    storage.create_evolution_comparison(base_id, base_id, child_id, 100, {"win_rate": 60.0}, "2026-01-02T00:00:00+00:00")

    result = lineage_explainer.explain_lineage(base_id)
    assert "still waiting" in result["narrative"].lower()


def test_endpoint_returns_the_narrative(test_db):
    from sindhu_web.api.evolution import strategy_lineage_explanation

    base_id = "lineage5"
    _seed_lineage(base_id)
    result = strategy_lineage_explanation(base_id)
    assert result["base_id"] == base_id


def test_endpoint_404s_for_unknown_lineage(test_db):
    from fastapi import HTTPException
    from sindhu_web.api.evolution import strategy_lineage_explanation

    try:
        strategy_lineage_explanation("does-not-exist")
        assert False, "expected an HTTPException"
    except HTTPException as e:
        assert e.status_code == 404
