"""Grand Feature Expansion, Phase 6 Feature 6: Feature Importance Ranking
(backtest_engine/feature_importance.py) -- a per-strategy leave-one-out
ablation, genuinely distinct from evolution_engine.mutator's
research_dna_correlations (ranks DNA-tag combinations across the WHOLE
POPULATION, never per-strategy). Reuses the same bounded in-memory re-run
infrastructure as what_if_simulator.py.
"""

import pytest

from backtest_engine import feature_importance
from backtest_engine.strategy_config import Condition, SLTPSpec, StrategyConfig


def _config(n_entry_conditions=2):
    conditions = [
        Condition(type="concept", name=f"concept_{i}")
        for i in range(n_entry_conditions)
    ]
    return StrategyConfig(
        name="Test Strategy",
        timeframes={"entry": "1m"},
        indicators=[],
        entry_conditions=conditions,
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0),
        take_profit=SLTPSpec(type="fixed_pct", value=2.0),
        risk_pct=1.0,
    )


def _batch(symbols=None, start_ms=0, end_ms=90 * 24 * 3600 * 1000):
    return {
        "exchange": "binance",
        "settings": {
            "initial_balance": 10000.0,
            "symbols": symbols if symbols is not None else ["BTCUSDT"],
            "start_ms": start_ms, "end_ms": end_ms,
        },
    }


def test_returns_none_when_batch_has_no_symbols(test_db):
    cfg = _config()
    assert feature_importance.rank_feature_importance(cfg, _batch(symbols=[])) is None


def test_too_few_conditions_returns_a_reason_not_a_ranking(monkeypatch, test_db):
    cfg = _config(n_entry_conditions=1)
    monkeypatch.setattr(feature_importance.optimizer, "_run_in_memory",
                         lambda *a, **k: {"total_trades": 1, "net_profit": 10.0})
    result = feature_importance.rank_feature_importance(cfg, _batch())
    assert result["conditions"] == []
    assert "reason" in result


def test_ranks_the_more_impactful_condition_first(monkeypatch, test_db):
    cfg = _config(n_entry_conditions=2)

    def fake_run_in_memory(config, exchange, symbol, settings, start_ms, end_ms):
        n = len(config.entry_conditions)
        if n == 2:
            return {"total_trades": 10, "net_profit": 100.0}  # baseline (both conditions)
        # Missing condition 0 (concept_0) tanks profit hard; missing
        # condition 1 (concept_1) barely matters.
        remaining_names = {c.name for c in config.entry_conditions}
        if "concept_0" not in remaining_names:
            return {"total_trades": 10, "net_profit": 10.0}
        return {"total_trades": 10, "net_profit": 95.0}

    monkeypatch.setattr(feature_importance.optimizer, "_run_in_memory", fake_run_in_memory)
    result = feature_importance.rank_feature_importance(cfg, _batch())
    assert result["baseline_net_profit"] == pytest.approx(100.0)
    assert len(result["conditions"]) == 2
    assert result["conditions"][0]["label"] == "concept_0"
    assert result["conditions"][0]["impact"] > result["conditions"][1]["impact"]


def test_does_not_mutate_the_original_config(monkeypatch, test_db):
    cfg = _config(n_entry_conditions=2)
    original_count = len(cfg.entry_conditions)
    monkeypatch.setattr(feature_importance.optimizer, "_run_in_memory",
                         lambda *a, **k: {"total_trades": 1, "net_profit": 10.0})
    feature_importance.rank_feature_importance(cfg, _batch())
    assert len(cfg.entry_conditions) == original_count


def test_caps_symbols_at_max_symbols(monkeypatch, test_db):
    cfg = _config()
    captured_symbols = set()

    def fake_run_in_memory(config, exchange, symbol, settings, start_ms, end_ms):
        captured_symbols.add(symbol)
        return {"total_trades": 1, "net_profit": 10.0}

    monkeypatch.setattr(feature_importance.optimizer, "_run_in_memory", fake_run_in_memory)
    feature_importance.rank_feature_importance(cfg, _batch(symbols=["A", "B", "C", "D", "E", "F"]), max_symbols=2)
    assert len(captured_symbols) == 2


def test_endpoint_runs_and_returns_rankings(test_db, monkeypatch, tmp_path):
    from backtest_engine import strategy_library as lib
    from sindhu_web.api.backtesting import FeatureImportanceRequest, run_feature_importance
    from data_engine import storage

    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path))
    lib.create(_config())
    storage.create_batch("batch1", "Test Strategy", "binance",
                          {"initial_balance": 10000.0, "symbols": ["BTCUSDT"], "start_ms": 0, "end_ms": 90 * 24 * 3600 * 1000},
                          "2026-01-01T00:00:00+00:00")
    monkeypatch.setattr(feature_importance.optimizer, "_run_in_memory",
                         lambda *a, **k: {"total_trades": 1, "net_profit": 10.0})
    result = run_feature_importance(FeatureImportanceRequest(batch_id="batch1"))
    assert len(result["conditions"]) == 2


def test_endpoint_404s_for_unknown_batch(test_db):
    from fastapi import HTTPException
    from sindhu_web.api.backtesting import FeatureImportanceRequest, run_feature_importance

    with pytest.raises(HTTPException) as exc_info:
        run_feature_importance(FeatureImportanceRequest(batch_id="does-not-exist"))
    assert exc_info.value.status_code == 404
