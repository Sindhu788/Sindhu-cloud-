"""Master Task 6, 2.1 -- proves the Evolution Engine's full tick
orchestration (EvolutionEngine._tick(), not just mutator.mutate_strategy()
in isolation, which the existing test_evolution_trade_gate.py already
covers) genuinely produces a new generation for an eligible lineage, and
genuinely SKIPS a zero-trade lineage from ever being enqueued -- the exact
queue-priority bug fixed in an earlier task (see engine.py's own docstring
at the "Master Task 4, Phase 1.3" comment in _tick()).

Governor.resource_ok() reads REAL live system CPU/RAM -- on this
particular 8GB dev machine, baseline RAM usage alone regularly sits at or
above the Governor's own 80% safety limit, which correctly prevents a real
tick from doing any work at all (this is the gate functioning exactly as
designed, not a bug -- see the Master Task 6 report for the live
confirmation of this on the real system). To test the ENGINE'S OWN
enqueue/mutate logic deterministically, independent of momentary real-
system load, resource_ok is mocked True here -- same category of
environment mock as any other test that doesn't want to depend on
incidental host state, and scoped ONLY to this isolated test_db, never to
a real production run."""

from unittest.mock import patch

from data_engine import storage
from evolution_engine import generation_manager
from evolution_engine.engine import EvolutionEngine

CONFIG = {"risk_reward": 2.0, "risk_pct": 1.0, "entry_timeframe": "5m"}


def _make_lineage(base_id, trades, evolution_score=50.0, now_iso="2026-01-01T00:00:00+00:00"):
    strategy_id = generation_manager.create_new_strategy_lineage(
        base_id, CONFIG, ["trend"], "sindhu_deterministic", False, "seed", now_iso, base_id=base_id,
    )
    storage.update_bot_strategy_result(
        strategy_id, evolution_score=evolution_score, score_breakdown={"_final_score": evolution_score},
        backtest_summary={"trades": trades, "win_rate": 50.0, "total_pnl": 100.0,
                           "avg_profit_factor": 1.5, "max_drawdown_pct": 5.0},
        now_iso=now_iso,
    )
    return strategy_id


def test_zero_trade_lineage_is_never_enqueued_or_mutated(test_db):
    """The actual bug: a lineage with zero real backtest trades can never
    pass the 100-trade evolution gate, so enqueuing it only burns a queue
    slot on a guaranteed no-op. After the fix, it's skipped before ever
    reaching the queue."""
    _make_lineage("BOT_ZERO", trades=0)
    engine = EvolutionEngine()
    with patch.object(engine.governor, "resource_ok", return_value=True):
        engine._tick()
    assert storage.latest_generation_for_base("BOT_ZERO")["generation"] == 1


def test_eligible_lineage_with_real_trades_produces_a_new_generation(test_db):
    """A genuinely eligible lineage (100+ real trades, matching rollback.
    should_evolve's threshold) must be enqueued and mutated by one real
    tick -- this is the "at least one new generation evaluated" evidence
    Master Task 6 asks for, produced deterministically rather than
    depending on live host resource availability."""
    _make_lineage("BOT_READY", trades=100)
    engine = EvolutionEngine()
    with patch.object(engine.governor, "resource_ok", return_value=True):
        engine._tick()
    latest = storage.latest_generation_for_base("BOT_READY")
    assert latest["generation"] == 2, "the tick should have produced a real second generation"


def test_a_tick_with_no_resources_available_mutates_nothing(test_db):
    """The Governor gate itself, exercised through the real engine: when
    resource_ok() is False, the tick must do zero mutation work, even for
    an otherwise fully-eligible lineage -- proving the safety gate is
    still fully wired into _tick(), not bypassed by this task's fix."""
    _make_lineage("BOT_READY2", trades=100)
    engine = EvolutionEngine()
    with patch.object(engine.governor, "resource_ok", return_value=False):
        engine._tick()
    assert storage.latest_generation_for_base("BOT_READY2")["generation"] == 1
