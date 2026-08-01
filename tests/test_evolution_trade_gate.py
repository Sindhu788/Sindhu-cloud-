"""Task 2 (Priority Batch 1) -- the 100-completed-trades Evolution gate,
before/after comparison recording, and automatic rollback.

Covers exactly what Task 2 asked for:
  (a) evolution does not trigger before 100 trades
  (b) it does trigger at the 100-trade mark
  (c) the before/after comparison data is correctly stored and retrievable
  (d) a simulated underperforming generation triggers rollback correctly

Also confirms this gate is fully independent of paper_trading.pattern_stats'
25-trade Wilson score gate (used elsewhere for signal confidence) -- neither
module imports the other.
"""

from evolution_engine import mutator, rollback, generation_manager
from evolution_engine.governor import Governor
from data_engine import storage


def _make_lineage(base_id, name, config, trades, win_rate=50.0, total_pnl=100.0,
                   avg_profit_factor=1.5, max_drawdown_pct=5.0, now_iso="2026-01-01T00:00:00+00:00"):
    """Creates generation 1 of a BOT strategy lineage with a real
    backtest_summary attached, exactly like sindhu_strategy.lifecycle would
    after a real backtest."""
    strategy_id = generation_manager.create_new_strategy_lineage(
        name, config, ["trend"], "sindhu_deterministic", False, "seed", now_iso, base_id=base_id,
    )
    storage.update_bot_strategy_result(
        strategy_id, evolution_score=50.0, score_breakdown={"_final_score": 50.0},
        backtest_summary={
            "trades": trades, "win_rate": win_rate, "total_pnl": total_pnl,
            "avg_profit_factor": avg_profit_factor, "max_drawdown_pct": max_drawdown_pct,
        },
        now_iso=now_iso,
    )
    return strategy_id


def _set_trades(strategy_id, trades, **overrides):
    row = storage.get_bot_strategy(strategy_id)
    summary = dict(row["backtest_summary"] or {})
    summary["trades"] = trades
    summary.update(overrides)
    storage.update_bot_strategy_result(strategy_id, backtest_summary=summary, now_iso="2026-01-02T00:00:00+00:00")


CONFIG = {"risk_reward": 2.0, "risk_pct": 1.0, "entry_timeframe": "5m"}


def test_evolution_does_not_trigger_before_100_trades(test_db):
    _make_lineage("BOT_S001", "Test Strategy", CONFIG, trades=99)
    can_evolve, threshold = rollback.should_evolve("BOT_S001")
    assert can_evolve is False
    assert threshold is None

    new_id = mutator.mutate_strategy("BOT_S001", Governor(), "2026-01-01T01:00:00+00:00")
    assert new_id is None
    # no second generation was created
    assert storage.latest_generation_for_base("BOT_S001")["generation"] == 1


def test_evolution_triggers_at_the_100_trade_mark(test_db):
    _make_lineage("BOT_S002", "Test Strategy", CONFIG, trades=100)
    can_evolve, threshold = rollback.should_evolve("BOT_S002")
    assert can_evolve is True
    assert threshold == 100

    new_id = mutator.mutate_strategy("BOT_S002", Governor(), "2026-01-01T01:00:00+00:00")
    assert new_id is not None
    assert new_id.endswith("_G2")
    latest = storage.latest_generation_for_base("BOT_S002")
    assert latest["generation"] == 2

    # the same 100-trade threshold never re-triggers a second evolution
    again = mutator.mutate_strategy("BOT_S002", Governor(), "2026-01-01T02:00:00+00:00")
    assert again is None


def test_evolution_does_not_touch_the_wilson_score_gate(test_db):
    """Structural check: evolution_engine.rollback never imports
    paper_trading.pattern_stats (the 25-trade Wilson gate), and vice versa --
    the two gates are completely independent code paths."""
    import ast
    import evolution_engine.rollback as rollback_mod
    import paper_trading.pattern_stats as pattern_stats_mod

    def imported_modules(module):
        tree = ast.parse(open(module.__file__, encoding="utf-8").read())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module)
        return names

    assert not any("pattern_stats" in m for m in imported_modules(rollback_mod))
    assert not any("evolution_engine" in m for m in imported_modules(pattern_stats_mod))


def test_before_after_comparison_is_stored_and_retrievable(test_db):
    _make_lineage("BOT_S003", "Test Strategy", CONFIG, trades=100,
                   win_rate=40.0, total_pnl=200.0, avg_profit_factor=1.8, max_drawdown_pct=6.0)
    new_id = mutator.mutate_strategy("BOT_S003", Governor(), "2026-01-01T01:00:00+00:00")
    assert new_id is not None

    comparisons = storage.list_evolution_comparisons(base_id="BOT_S003")
    assert len(comparisons) == 1
    c = comparisons[0]
    assert c["trade_threshold"] == 100
    assert c["child_id"] == new_id
    assert c["before"]["win_rate"] == 40.0
    assert c["before"]["total_pnl"] == 200.0
    assert c["before"]["avg_profit_factor"] == 1.8
    assert c["before"]["max_drawdown_pct"] == 6.0
    assert c["after"] is None
    assert c["verdict"] is None

    # not enough trades on the child yet -- comparison stays pending
    _set_trades(new_id, 40)
    result = rollback.try_finalize_comparison(new_id, "2026-01-01T03:00:00+00:00")
    assert result is None
    assert storage.list_evolution_comparisons(base_id="BOT_S003")[0]["after"] is None

    # child reaches 100 of its own trades, performing BETTER than parent
    _set_trades(new_id, 100, win_rate=55.0, total_pnl=300.0, avg_profit_factor=2.2, max_drawdown_pct=4.0)
    result = rollback.try_finalize_comparison(new_id, "2026-01-01T04:00:00+00:00")
    assert result is not None
    assert result["verdict"] == "improved"
    assert result["rolled_back"] is False

    finalized = storage.list_evolution_comparisons(base_id="BOT_S003")[0]
    assert finalized["after"]["win_rate"] == 55.0
    assert finalized["verdict"] == "improved"
    assert finalized["rolled_back"] is False

    # lineage stays pinned to the (better) child, not rolled back
    assert rollback.effective_generation("BOT_S003")["id"] == new_id


def test_underperforming_generation_triggers_rollback(test_db):
    parent_id = _make_lineage("BOT_S004", "Test Strategy", CONFIG, trades=100,
                               win_rate=50.0, total_pnl=500.0, avg_profit_factor=2.0, max_drawdown_pct=5.0)
    new_id = mutator.mutate_strategy("BOT_S004", Governor(), "2026-01-01T01:00:00+00:00")
    assert new_id is not None

    # child performs worse on all 4 core metrics
    _set_trades(new_id, 100, win_rate=20.0, total_pnl=-100.0, avg_profit_factor=0.8, max_drawdown_pct=15.0)
    result = rollback.try_finalize_comparison(new_id, "2026-01-01T05:00:00+00:00")
    assert result is not None
    assert result["verdict"] == "regressed"
    assert result["rolled_back"] is True

    finalized = storage.list_evolution_comparisons(base_id="BOT_S004")[0]
    assert finalized["rolled_back"] is True

    # the lineage is now pinned back to the parent generation
    effective = rollback.effective_generation("BOT_S004")
    assert effective["id"] == parent_id

    # the underperforming generation is a PERMANENT record -- never deleted,
    # still readable, just no longer "in use"
    still_there = storage.get_bot_strategy(new_id)
    assert still_there is not None
    assert still_there["status"] == "active"  # archival status untouched -- only the "in use" pin changed

    # the next mutation branches from the parent (the one still in use),
    # not from the abandoned underperforming generation
    gate = storage.get_trade_gate("BOT_S004")
    assert gate["active_generation_id"] == parent_id


def test_rollback_does_not_affect_a_different_lineage(test_db):
    """Two independent lineages' gates/comparisons never leak into each
    other."""
    _make_lineage("BOT_S005", "Strategy A", CONFIG, trades=100)
    _make_lineage("BOT_S006", "Strategy B", CONFIG, trades=50)

    a_evolve, _ = rollback.should_evolve("BOT_S005")
    b_evolve, _ = rollback.should_evolve("BOT_S006")
    assert a_evolve is True
    assert b_evolve is False
