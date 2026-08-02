"""Batch 3, Task 4 (Part A) -- the real gap that kept the Evolution
Engine's self-learning loop idle: the daily generator (and the engine's
own mutation step) create new BOT strategy generations, but nothing ever
gave any of them a first real backtest, so none could ever accumulate
the trades needed to reach Batch 1's 100-trade evolution gate.
evolution_engine.engine.EvolutionEngine._backtest_untested_candidates
closes that gap. Never touches the 100-trade gate or rollback mechanism
themselves -- only ever feeds them real data.
"""

from unittest.mock import patch

from data_engine import storage, config as base_config
from evolution_engine import generation_manager
from evolution_engine.engine import EvolutionEngine
from evolution_engine.governor import Governor


def _make_untested_lineage(base_id, name="Untested Candidate"):
    config = {"risk_reward": 2.0, "risk_pct": 1.0, "entry_timeframe": "5m"}
    return generation_manager.create_new_strategy_lineage(
        name, config, ["trend"], "sindhu_deterministic", False, "seed", "2026-01-01T00:00:00+00:00", base_id=base_id,
    )


def _engine():
    e = EvolutionEngine(governor=Governor())
    e.job_id = "evo_test"
    return e


# ------------------------------------------------------------ storage.list_untested_bot_strategies

def test_list_untested_bot_strategies_finds_candidates_with_no_backtest(test_db):
    strategy_id = _make_untested_lineage("BOT_S001")
    untested = storage.list_untested_bot_strategies(limit=10)
    assert any(r["id"] == strategy_id for r in untested)


def test_list_untested_bot_strategies_excludes_already_backtested(test_db):
    strategy_id = _make_untested_lineage("BOT_S002")
    storage.update_bot_strategy_result(
        strategy_id, evolution_score=50.0, backtest_summary={"trades": 10}, now_iso="2026-01-01T01:00:00+00:00",
    )
    untested = storage.list_untested_bot_strategies(limit=50)
    assert not any(r["id"] == strategy_id for r in untested)


def test_list_untested_bot_strategies_respects_limit(test_db):
    for i in range(5):
        _make_untested_lineage(f"BOT_S{i:03d}", name=f"Candidate {i}")
    untested = storage.list_untested_bot_strategies(limit=2)
    assert len(untested) == 2


# ------------------------------------------------------------ EvolutionEngine._backtest_untested_candidates

def test_backtest_untested_candidates_runs_the_real_pipeline_for_one_candidate(test_db, tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    base_config.save_config("exchanges.json", {"default": "binance"})
    storage.save_symbols("binance", ["BTCUSDT"], "2026-01-01T00:00:00+00:00")
    strategy_id = _make_untested_lineage("BOT_S010")

    fake_result = {"validated": True, "errors": [], "batch_id": "b1",
                    "backtest_summary": {"trades": 42}, "evolution_score": 55.0}
    e = _engine()
    with patch.object(e.governor, "resource_ok", return_value=True), \
         patch("evolution_engine.engine.sindhu_lifecycle.validate_and_backtest", return_value=fake_result) as mock_bt:
        tested = e._backtest_untested_candidates("2026-01-01T02:00:00+00:00")

    assert len(tested) == 1
    assert tested[0]["id"] == strategy_id
    assert tested[0]["trades"] == 42
    mock_bt.assert_called_once()
    call_args = mock_bt.call_args
    assert call_args[0][0] == strategy_id
    assert call_args[1]["use_multiprocessing"] is False  # lightweight, single-process


def test_backtest_untested_candidates_respects_the_per_tick_limit(test_db, tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    base_config.save_config("exchanges.json", {"default": "binance"})
    storage.save_symbols("binance", ["BTCUSDT"], "2026-01-01T00:00:00+00:00")
    for i in range(5):
        _make_untested_lineage(f"BOT_S1{i}", name=f"Candidate {i}")

    fake_result = {"validated": True, "errors": [], "batch_id": "b1",
                    "backtest_summary": {"trades": 10}, "evolution_score": 50.0}
    e = _engine()
    with patch.object(e.governor, "resource_ok", return_value=True), \
         patch("evolution_engine.engine.sindhu_lifecycle.validate_and_backtest", return_value=fake_result) as mock_bt:
        tested = e._backtest_untested_candidates("2026-01-01T02:00:00+00:00")

    # UNTESTED_CANDIDATES_PER_TICK == 1 -- never blasts through the whole backlog at once
    assert len(tested) == 1
    assert mock_bt.call_count == 1


def test_backtest_untested_candidates_skips_entirely_when_resources_are_tight(test_db, tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    base_config.save_config("exchanges.json", {"default": "binance"})
    storage.save_symbols("binance", ["BTCUSDT"], "2026-01-01T00:00:00+00:00")
    _make_untested_lineage("BOT_S020")

    e = _engine()
    with patch.object(e.governor, "resource_ok", return_value=False), \
         patch("evolution_engine.engine.sindhu_lifecycle.validate_and_backtest") as mock_bt:
        tested = e._backtest_untested_candidates("2026-01-01T02:00:00+00:00")

    assert tested == []
    mock_bt.assert_not_called()


def test_backtest_untested_candidates_does_nothing_when_no_coins_downloaded_yet(test_db, tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    base_config.save_config("exchanges.json", {"default": "binance"})
    _make_untested_lineage("BOT_S030")

    e = _engine()
    with patch("evolution_engine.engine.sindhu_lifecycle.validate_and_backtest") as mock_bt:
        tested = e._backtest_untested_candidates("2026-01-01T02:00:00+00:00")

    assert tested == []
    mock_bt.assert_not_called()


def test_backtest_untested_candidates_never_touches_the_100_trade_gate_directly(test_db, tmp_path, monkeypatch):
    """This mechanism only ever produces trade DATA -- it must never itself
    decide mutation eligibility or call into evolution_engine.rollback."""
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    base_config.save_config("exchanges.json", {"default": "binance"})
    storage.save_symbols("binance", ["BTCUSDT"], "2026-01-01T00:00:00+00:00")
    strategy_id = _make_untested_lineage("BOT_S040")

    fake_result = {"validated": True, "errors": [], "batch_id": "b1",
                    "backtest_summary": {"trades": 150}, "evolution_score": 60.0}
    e = _engine()
    with patch.object(e.governor, "resource_ok", return_value=True), \
         patch("evolution_engine.engine.sindhu_lifecycle.validate_and_backtest", return_value=fake_result), \
         patch("evolution_engine.rollback.record_evolution_event") as mock_rollback_event, \
         patch("evolution_engine.rollback.try_finalize_comparison") as mock_finalize:
        e._backtest_untested_candidates("2026-01-01T02:00:00+00:00")

    mock_rollback_event.assert_not_called()
    mock_finalize.assert_not_called()
