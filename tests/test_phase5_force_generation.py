"""Grand Master Batch, Phase 5 Item 4 -- manual "Force New Generation".

Bypasses ONLY should_evolve's trade-count throttle; the separate 100-
real-trade gate that judges whether a new generation gets KEPT
(rollback.try_finalize_comparison) is completely untouched.
"""

from evolution_engine import mutator, rollback, generation_manager
from evolution_engine.governor import Governor
from data_engine import storage
from sindhu_web.api.evolution import force_new_generation

CONFIG = {"risk_reward": 2.0, "risk_pct": 1.0, "entry_timeframe": "5m"}


def _make_lineage(base_id, trades, now_iso="2026-01-01T00:00:00+00:00"):
    strategy_id = generation_manager.create_new_strategy_lineage(
        "Test Strategy", CONFIG, ["trend"], "sindhu_deterministic", False, "seed", now_iso, base_id=base_id,
    )
    storage.update_bot_strategy_result(
        strategy_id, evolution_score=50.0, score_breakdown={"_final_score": 50.0},
        backtest_summary={"trades": trades, "win_rate": 50.0, "total_pnl": 100.0,
                           "avg_profit_factor": 1.5, "max_drawdown_pct": 5.0},
        now_iso=now_iso,
    )
    return strategy_id


def test_normal_mutate_still_refuses_below_100_trades(test_db):
    _make_lineage("BOT_S001", trades=10)
    new_id = mutator.mutate_strategy("BOT_S001", Governor(), "2026-01-01T01:00:00+00:00")
    assert new_id is None


def test_force_true_creates_a_generation_below_100_trades(test_db):
    _make_lineage("BOT_S001", trades=10)
    new_id = mutator.mutate_strategy("BOT_S001", Governor(), "2026-01-01T01:00:00+00:00", force=True)
    assert new_id is not None
    assert storage.latest_generation_for_base("BOT_S001")["generation"] == 2


def test_forced_generation_still_needs_100_trades_before_being_judged(test_db):
    _make_lineage("BOT_S001", trades=10)
    new_id = mutator.mutate_strategy("BOT_S001", Governor(), "2026-01-01T01:00:00+00:00", force=True)

    # The forced child has 0 trades of its own -- try_finalize_comparison
    # must refuse to judge it yet, exactly like a naturally-created one.
    result = rollback.try_finalize_comparison(new_id, "2026-01-01T02:00:00+00:00")
    assert result is None

    pending = storage.get_pending_comparison_for_child(new_id)
    assert pending is not None
    assert pending["after"] is None  # still un-judged


def test_force_new_generation_endpoint_returns_the_new_id(test_db):
    _make_lineage("BOT_S001", trades=5)
    result = force_new_generation("BOT_S001")
    assert "new_generation_id" in result
    assert storage.latest_generation_for_base("BOT_S001")["generation"] == 2


def test_force_new_generation_endpoint_404s_for_unknown_lineage(test_db):
    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        force_new_generation("does-not-exist")
