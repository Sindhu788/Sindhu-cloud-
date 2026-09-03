"""Grand Feature Expansion, Phase 6 Feature 9: Regime-Aware Evolution
(evolution_engine/mutator.py's regime_context_for) -- fixes a real,
pre-existing dead-code bug: mutate_strategy's own regime-adaptation
branch already existed, but its only real caller (evolution_engine.
engine._tick) never passed exchange/symbol/timeframe, so the branch
never fired in production. regime_context_for derives all 3 from the
lineage's own latest real backtest batch.
"""

import pandas as pd
import pytest

from data_engine import storage
from evolution_engine import generation_manager, market_regime, mutator

CONFIG = {"risk_reward": 2.0, "risk_pct": 1.0, "timeframes": {"entry": "1h"}}


def _seed_lineage_with_batch(base_id, symbols=None):
    generation_manager.create_new_strategy_lineage(
        "Gen1", CONFIG, ["trend"], "sindhu_deterministic", False, "seed", "2026-01-01T00:00:00+00:00", base_id=base_id,
    )
    storage.create_batch(
        "batch1", "Gen1", "binance",
        {"initial_balance": 10000.0, "symbols": symbols or ["BTCUSDT"], "start_ms": 0, "end_ms": 1000},
        "2026-01-01T00:00:00+00:00",
    )
    storage.update_bot_strategy_result(
        f"{base_id}_G1", evolution_score=50.0, score_breakdown={"_final_score": 50.0},
        backtest_summary={"batch_id": "batch1", "trades": 10}, now_iso="2026-01-01T00:00:00+00:00",
    )


def test_no_lineage_returns_none_triple(test_db):
    assert mutator.regime_context_for("does-not-exist") == (None, None, None)


def test_lineage_with_no_batch_yet_returns_none_triple(test_db):
    base_id = "lineage1"
    generation_manager.create_new_strategy_lineage(
        "Gen1", CONFIG, ["trend"], "sindhu_deterministic", False, "seed", "2026-01-01T00:00:00+00:00", base_id=base_id,
    )
    assert mutator.regime_context_for(base_id) == (None, None, None)


def test_lineage_with_a_real_batch_derives_exchange_symbol_timeframe(test_db):
    base_id = "lineage2"
    _seed_lineage_with_batch(base_id, symbols=["ETHUSDT", "BTCUSDT"])
    exchange, symbol, timeframe = mutator.regime_context_for(base_id)
    assert exchange == "binance"
    assert symbol == "ETHUSDT"  # first symbol in the batch's own symbol list
    assert timeframe == "1h"


def test_mutate_strategy_actually_applies_regime_adaptation_when_context_resolves(test_db, monkeypatch):
    base_id = "lineage3"
    _seed_lineage_with_batch(base_id)
    # Cross the 100-trade evolution gate.
    storage.update_bot_strategy_result(
        f"{base_id}_G1", backtest_summary={"batch_id": "batch1", "trades": 100},
        now_iso="2026-01-01T00:00:00+00:00",
    )
    monkeypatch.setattr(market_regime, "detect_regime", lambda *a, **k: "volatile")

    from evolution_engine.governor import Governor
    gov = Governor()
    reg_exchange, reg_symbol, reg_timeframe = mutator.regime_context_for(base_id)
    assert reg_exchange is not None  # context actually resolved -- the whole point of this feature
    new_id = mutator.mutate_strategy(base_id, gov, "2026-01-02T00:00:00+00:00",
                                      exchange=reg_exchange, symbol=reg_symbol, timeframe=reg_timeframe)
    assert new_id is not None
    child = storage.get_bot_strategy(new_id)
    assert "regime=volatile" in child["mutation_reason"]
