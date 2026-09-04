"""Master Task 4, Phase 1.3 -- a real, verified bug found while auditing the
live Evolution Engine: it had produced ZERO generations in 6 days of
continuous ticking (evolution_comparisons table empty, every bot_strategy
still at generation 1) despite several real lineages having thousands of
backtested trades and genuinely passing rollback.should_evolve's 100-trade
gate. Root-caused to two compounding bugs, both fixed here:

1. evolution_engine/governor.py's Governor.enqueue() rejected any item once
   the queue was full, regardless of whether the new item was a BETTER
   (lower-priority-number) candidate than the worst one already queued. With
   198 real lineages and a 20-slot queue, whichever 20 were enqueued FIRST
   (storage.list_bot_strategy_base_ids() has no ORDER BY) monopolized every
   single tick forever -- verified live via a direct query against the
   production database.

2. evolution_engine/engine.py's _tick() enqueued EVERY lineage into the
   mutation queue, including ones with zero real backtest trades -- which
   can never pass rollback.should_evolve's gate (trades < threshold), so
   enqueuing them only ever wasted a queue slot and (worse) one of the
   tick's scarce MAX_EXPERIMENTS_PER_RUN dequeue attempts on a guaranteed
   no-op. Verified live: of 198 lineages, 179 had zero real trades, and
   their evolution_score (27.5, from scoring.py's own component defaults)
   happened to rank as MORE urgent than the 19 genuinely tested lineages'
   real scores (~31.4-32.9) -- so untested lineages always won the priority
   race and ate the whole per-tick experiment budget.

Neither fix touches the 100-trade gate itself, the Governor's CPU/RAM
limits, or MAX_GENERATIONS_PER_STRATEGY -- both are pure scheduling-fairness
fixes so the existing, unweakened gate actually gets a chance to say yes.
"""

from unittest.mock import patch

import pytest

from data_engine import storage
from evolution_engine import generation_manager
from evolution_engine.engine import EvolutionEngine
from evolution_engine.governor import Governor, QueueFullError


# ------------------------------------------------------------ Governor.enqueue eviction

def test_enqueue_fills_empty_slots_normally():
    g = Governor(max_queue_size=3)
    g.enqueue("a", priority=10)
    g.enqueue("b", priority=5)
    g.enqueue("c", priority=20)
    assert g.queue_size() == 3


def test_enqueue_evicts_the_worst_item_when_full_and_new_item_is_better():
    g = Governor(max_queue_size=2)
    g.enqueue("bad", priority=90)
    g.enqueue("mediocre", priority=50)
    # Full now (2/2). "urgent" (priority 10) beats the current worst (90).
    g.enqueue("urgent", priority=10)
    items = {item for _, _, item in g._queue}
    assert items == {"urgent", "mediocre"}
    assert "bad" not in items


def test_enqueue_rejects_an_item_worse_than_everything_already_queued():
    g = Governor(max_queue_size=2)
    g.enqueue("good", priority=5)
    g.enqueue("better", priority=1)
    with pytest.raises(QueueFullError):
        g.enqueue("worse", priority=99)
    items = {item for _, _, item in g._queue}
    assert items == {"good", "better"}


def test_try_enqueue_returns_false_only_when_genuinely_not_an_improvement():
    g = Governor(max_queue_size=1)
    assert g.try_enqueue("first", priority=50) is True
    assert g.try_enqueue("worse", priority=80) is False
    assert g.try_enqueue("better", priority=10) is True
    items = {item for _, _, item in g._queue}
    assert items == {"better"}


def test_198_candidates_20_slots_the_20_real_lowest_priorities_all_win():
    """Directly reproduces the scale of the live bug: many more real
    candidates than queue slots, arriving in an arbitrary (not
    priority-sorted) order -- the queue must still end up holding exactly
    the true top-K by priority, not just "whichever came first"."""
    g = Governor(max_queue_size=20)
    # Deliberately NOT priority-sorted on arrival, and the genuinely best
    # (lowest) priorities are scattered near the end -- exactly what a
    # plain "reject when full" queue gets wrong.
    for i in range(198):
        g.try_enqueue(f"lineage_{i}", priority=100 - i)  # priorities 100 down to -97
    final_items = {item for _, _, item in g._queue}
    expected_winners = {f"lineage_{i}" for i in range(178, 198)}  # priorities 22 down to -97, the 20 lowest
    assert final_items == expected_winners


# ------------------------------------------------------------ EvolutionEngine._tick: real trades required to enter the queue

def _make_lineage(base_id, trades=0, evolution_score=None, name=None):
    config = {"risk_reward": 2.0, "risk_pct": 1.0, "entry_timeframe": "5m"}
    strategy_id = generation_manager.create_new_strategy_lineage(
        name or f"Lineage {base_id}", config, ["trend"], "sindhu_deterministic", False, "seed",
        "2026-01-01T00:00:00+00:00", base_id=base_id,
    )
    if trades > 0 or evolution_score is not None:
        storage.update_bot_strategy_result(
            strategy_id,
            evolution_score=evolution_score if evolution_score is not None else 27.5,
            backtest_summary={"trades": trades},
            now_iso="2026-01-01T01:00:00+00:00",
        )
    return strategy_id


def _engine_with_stubbed_heavy_steps():
    e = EvolutionEngine(governor=Governor())
    e.job_id = "evo_test"
    return e


def test_tick_never_enqueues_a_lineage_with_zero_real_trades(test_db):
    _make_lineage("BOT_UNTESTED", trades=0, evolution_score=27.5)
    _make_lineage("BOT_TESTED", trades=4000, evolution_score=31.5)

    e = _engine_with_stubbed_heavy_steps()
    enqueued = []
    with patch.object(e.governor, "resource_ok", return_value=True), \
         patch.object(e, "_backtest_untested_candidates", return_value=[]), \
         patch.object(e.governor, "try_enqueue", side_effect=lambda item, priority: enqueued.append(item) or True), \
         patch("evolution_engine.engine.mutator.regime_context_for", return_value=(None, None, None)), \
         patch("evolution_engine.engine.mutator.mutate_strategy", return_value=None), \
         patch("evolution_engine.engine.mutator.archive_underperformers", return_value=[]), \
         patch("evolution_engine.engine.champion.recompute_champions", return_value={}):
        e._tick()

    assert "BOT_TESTED" in enqueued
    assert "BOT_UNTESTED" not in enqueued


def test_tick_lets_a_genuinely_eligible_low_priority_lineage_actually_mutate(test_db):
    """End-to-end reproduction of the live fix: many untested lineages
    (which used to win the priority race and eat the whole experiment
    budget) must no longer prevent a real, gate-eligible lineage from
    reaching mutate_strategy and producing a new generation."""
    for i in range(30):
        _make_lineage(f"BOT_NOISE{i:02d}", trades=0, evolution_score=27.5)
    _make_lineage("BOT_REAL", trades=4000, evolution_score=31.5)

    e = _engine_with_stubbed_heavy_steps()
    with patch.object(e.governor, "resource_ok", return_value=True), \
         patch.object(e, "_backtest_untested_candidates", return_value=[]), \
         patch("evolution_engine.engine.mutator.regime_context_for", return_value=(None, None, None)), \
         patch("evolution_engine.engine.mutator.archive_underperformers", return_value=[]), \
         patch("evolution_engine.engine.champion.recompute_champions", return_value={}):
        e._tick()

    generations = storage.list_bot_strategies(base_id="BOT_REAL", limit=10)
    assert len(generations) == 2, "BOT_REAL should have mutated to a real Gen 2"
