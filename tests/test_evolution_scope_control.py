"""Master 15-Item task, Item 13: Evolution Scope Control (Conservative/
Balanced/Aggressive Evolution Mode). Conservative is the new default --
tests that don't explicitly set a mode exercise the new default behavior,
same as it will be for a real fresh install."""
from unittest.mock import patch

import pytest

from data_engine import config as base_config, storage
from evolution_engine import generation_manager, mutator, config as evo_config
from evolution_engine.engine import EvolutionEngine

CONFIG = {"risk_reward": 2.0, "risk_pct": 1.0, "entry_timeframe": "5m"}


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """evolution_engine/config.py persists to data/config/evolution_settings.json
    via the same base_config.CONFIG_DIR every other settings file in this
    project uses -- isolated here so these tests never read/write the
    real project's saved Evolution Mode."""
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _make_lineage(base_id, trades, avg_profit_factor, evolution_score=50.0, now_iso="2026-01-01T00:00:00+00:00"):
    strategy_id = generation_manager.create_new_strategy_lineage(
        base_id, CONFIG, ["trend"], "sindhu_deterministic", False, "seed", now_iso, base_id=base_id,
    )
    storage.update_bot_strategy_result(
        strategy_id, evolution_score=evolution_score, score_breakdown={"_final_score": evolution_score},
        backtest_summary={"trades": trades, "win_rate": 50.0, "total_pnl": 100.0,
                           "avg_profit_factor": avg_profit_factor, "max_drawdown_pct": 5.0},
        now_iso=now_iso,
    )
    return strategy_id


def test_conservative_is_the_default_mode():
    mode, params = evo_config.current_mode_params()
    assert mode == "conservative"
    assert params["max_generations"] == 3
    assert params["min_profit_factor"] == 0.7
    assert params["min_trades"] == 25


def test_eligibility_predicate_passes_on_either_bar_alone():
    params = evo_config.MODE_PARAMS["conservative"]
    # trades bar alone
    assert mutator.is_eligible_for_mode({"trades": 25, "avg_profit_factor": 0.1}, "conservative", params) is True
    # profit factor bar alone
    assert mutator.is_eligible_for_mode({"trades": 5, "avg_profit_factor": 0.7}, "conservative", params) is True
    # neither bar
    assert mutator.is_eligible_for_mode({"trades": 5, "avg_profit_factor": 0.3}, "conservative", params) is False
    # balanced/aggressive have no per-strategy minimum bar
    assert mutator.is_eligible_for_mode({"trades": 0, "avg_profit_factor": 0.0}, "balanced", evo_config.MODE_PARAMS["balanced"]) is True
    assert mutator.is_eligible_for_mode({"trades": 0, "avg_profit_factor": 0.0}, "aggressive", evo_config.MODE_PARAMS["aggressive"]) is True


def test_conservative_mode_skips_a_weak_lineage_even_with_real_trades(test_db):
    """A real simulated case: 30 completed trades (clears the OLD 25-trade
    Wilson-style intuition) but a genuinely weak 0.3 Profit Factor -- under
    Conservative mode this must never be enqueued/mutated at all."""
    _make_lineage("BOT_WEAK", trades=30, avg_profit_factor=0.3)
    engine = EvolutionEngine()
    with patch.object(engine.governor, "resource_ok", return_value=True):
        engine._tick()
    assert storage.latest_generation_for_base("BOT_WEAK")["generation"] == 1


def test_conservative_mode_allows_a_lineage_clearing_the_trades_bar(test_db):
    """100 real trades clears both Conservative's 25-trade eligibility bar
    AND the older, unrelated 100-trade should_evolve gate in rollback.py --
    a real end-to-end proof a genuinely eligible lineage still gets a new
    generation under the new default mode."""
    _make_lineage("BOT_ELIGIBLE", trades=100, avg_profit_factor=0.3)
    engine = EvolutionEngine()
    with patch.object(engine.governor, "resource_ok", return_value=True):
        engine._tick()
    assert storage.latest_generation_for_base("BOT_ELIGIBLE")["generation"] == 2


def test_aggressive_mode_restores_original_unrestricted_behavior(test_db):
    """The exact lineage that Conservative mode correctly skips (weak PF,
    real trades but under the eligibility bar) must still get a new
    generation once the CEO explicitly opts into Aggressive mode --
    proving this task didn't silently change Aggressive's own behavior."""
    evo_config.save({"evolution_mode": "aggressive"})
    _make_lineage("BOT_AGGRESSIVE", trades=100, avg_profit_factor=0.1)
    engine = EvolutionEngine()
    with patch.object(engine.governor, "resource_ok", return_value=True):
        engine._tick()
    assert storage.latest_generation_for_base("BOT_AGGRESSIVE")["generation"] == 2


def test_is_matured_true_once_generation_cap_reached(test_db):
    base_id = "BOT_CAPTEST"
    generation_manager.create_new_strategy_lineage(base_id, CONFIG, [], "x", False, "seed", "2026-01-01T00:00:00+00:00", base_id=base_id)
    assert mutator.is_matured(base_id, max_generations=3) is False
    generation_manager.create_next_strategy_generation(base_id, "n2", CONFIG, [], "x", False, "r", "2026-01-01T00:00:00+00:00", max_generations=10)
    generation_manager.create_next_strategy_generation(base_id, "n3", CONFIG, [], "x", False, "r", "2026-01-01T00:00:00+00:00", max_generations=10)
    assert mutator.is_matured(base_id, max_generations=3) is True


def test_is_matured_true_after_two_consecutive_non_improving_generations(test_db):
    base_id = "BOT_PLATEAU"
    now = "2026-01-01T00:00:00+00:00"
    sid1 = generation_manager.create_new_strategy_lineage(base_id, CONFIG, [], "x", False, "seed", now, base_id=base_id)
    storage.update_bot_strategy_result(sid1, evolution_score=60.0, score_breakdown={}, backtest_summary={"trades": 100}, now_iso=now)
    sid2 = generation_manager.create_next_strategy_generation(base_id, "n2", CONFIG, [], "x", False, "r", now, max_generations=10)
    storage.update_bot_strategy_result(sid2, evolution_score=55.0, score_breakdown={}, backtest_summary={"trades": 100}, now_iso=now)
    assert mutator.is_matured(base_id, max_generations=10) is False, "only ONE non-improving generation so far"
    sid3 = generation_manager.create_next_strategy_generation(base_id, "n3", CONFIG, [], "x", False, "r", now, max_generations=10)
    storage.update_bot_strategy_result(sid3, evolution_score=50.0, score_breakdown={}, backtest_summary={"trades": 100}, now_iso=now)
    assert mutator.is_matured(base_id, max_generations=10) is True, "TWO consecutive non-improving generations in a row"


def test_matured_lineage_is_never_auto_enqueued_in_conservative_mode(test_db):
    base_id = "BOT_MATURED_SKIP"
    now = "2026-01-01T00:00:00+00:00"
    sid = _make_lineage(base_id, trades=100, avg_profit_factor=1.0, evolution_score=60.0, now_iso=now)
    # push it to the Conservative generation cap (3) manually
    generation_manager.create_next_strategy_generation(base_id, "n2", CONFIG, [], "x", False, "r", now, max_generations=10)
    generation_manager.create_next_strategy_generation(base_id, "n3", CONFIG, [], "x", False, "r", now, max_generations=10)
    assert storage.latest_generation_for_base(base_id)["generation"] == 3

    engine = EvolutionEngine()
    with patch.object(engine.governor, "resource_ok", return_value=True):
        engine._tick()
    # matured at the cap -- must NOT get a 4th generation automatically
    assert storage.latest_generation_for_base(base_id)["generation"] == 3
