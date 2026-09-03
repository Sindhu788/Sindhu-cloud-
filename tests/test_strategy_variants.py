"""Grand Feature Expansion, Phase 6 Feature 5: Self-Generated Strategy
Variants (backtest_engine/strategy_variants.py) -- branches several
PARALLEL sibling variants off ONE existing strategy and tests them side-
by-side, genuinely distinct from deterministic_builder (independent new
candidates) and mutator.py (exactly one sequential next generation per
tick). Reuses the same bounded fast-window re-run infrastructure as
what_if_simulator.py / feature_importance.py.
"""

import pytest

from backtest_engine import strategy_variants
from backtest_engine.strategy_config import Condition, SLTPSpec, StrategyConfig


def _config(entry_condition_name="support"):
    return StrategyConfig(
        name="Test Strategy",
        timeframes={"entry": "1m"},
        indicators=[],
        entry_conditions=[Condition(type="concept", name=entry_condition_name)],
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


def test_generate_variants_swaps_one_concept_for_a_same_category_alternative():
    cfg = _config("support")  # "support" is DNA-tagged "liquidity" only
    variants = strategy_variants.generate_variants(cfg, max_variants=4)
    assert len(variants) == 4
    for v in variants:
        assert v["config"].entry_conditions[0].name != "support"
        assert "support" in v["label"]


def test_generate_variants_never_mutates_the_original_config():
    cfg = _config("support")
    strategy_variants.generate_variants(cfg)
    assert cfg.entry_conditions[0].name == "support"


def test_no_concept_condition_produces_no_variants():
    cfg = StrategyConfig(
        name="Indicator Only", timeframes={"entry": "1m"},
        indicators=[{"name": "rsi", "params": {"period": 14}, "role": "entry"}],
        entry_conditions=[Condition(type="indicator_compare", indicator="rsi", op="<", value=30.0)],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0), take_profit=SLTPSpec(type="fixed_pct", value=2.0),
        risk_pct=1.0,
    )
    assert strategy_variants.generate_variants(cfg) == []


def test_returns_none_when_batch_has_no_usable_range(test_db):
    cfg = _config()
    assert strategy_variants.test_variants(cfg, _batch(symbols=[])) is None


def test_no_variants_returns_a_reason(monkeypatch, test_db):
    cfg = StrategyConfig(
        name="Indicator Only", timeframes={"entry": "1m"}, indicators=[],
        entry_conditions=[Condition(type="indicator_compare", indicator="rsi", op="<", value=30.0)],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0), take_profit=SLTPSpec(type="fixed_pct", value=2.0),
        risk_pct=1.0,
    )
    monkeypatch.setattr(strategy_variants.optimizer, "_run_in_memory",
                         lambda *a, **k: {"total_trades": 1, "net_profit": 10.0})
    result = strategy_variants.test_variants(cfg, _batch())
    assert result["variants"] == []
    assert "reason" in result


def test_variants_are_ranked_by_improvement(monkeypatch, test_db):
    cfg = _config("support")

    def fake_run_in_memory(config, exchange, symbol, settings, start_ms, end_ms):
        name = config.entry_conditions[0].name
        if name == "support":
            return {"total_trades": 10, "net_profit": 100.0}
        # Every alternative concept gets a distinct, deterministic profit
        # based on its name -- makes the expected ranking order derivable
        # regardless of which alternatives generate_variants happens to draw.
        return {"total_trades": 10, "net_profit": float(len(name) * 10)}

    monkeypatch.setattr(strategy_variants.optimizer, "_run_in_memory", fake_run_in_memory)
    result = strategy_variants.test_variants(cfg, _batch(), max_variants=4)
    assert result["baseline_net_profit"] == pytest.approx(100.0)
    assert len(result["variants"]) == 4
    # Ranked descending by improvement -- the first result's improvement
    # must be the maximum across every returned variant.
    improvements = [v["improvement"] for v in result["variants"]]
    assert improvements == sorted(improvements, reverse=True)


def test_endpoint_runs_and_returns_variants(test_db, monkeypatch, tmp_path):
    from backtest_engine import strategy_library as lib
    from sindhu_web.api.backtesting import StrategyVariantsRequest, run_strategy_variants
    from data_engine import storage

    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path))
    lib.create(_config("support"))
    storage.create_batch("batch1", "Test Strategy", "binance",
                          {"initial_balance": 10000.0, "symbols": ["BTCUSDT"], "start_ms": 0, "end_ms": 90 * 24 * 3600 * 1000},
                          "2026-01-01T00:00:00+00:00")
    monkeypatch.setattr(strategy_variants.optimizer, "_run_in_memory",
                         lambda *a, **k: {"total_trades": 1, "net_profit": 10.0})
    result = run_strategy_variants(StrategyVariantsRequest(batch_id="batch1"))
    assert len(result["variants"]) == 4


def test_endpoint_404s_for_unknown_batch(test_db):
    from fastapi import HTTPException
    from sindhu_web.api.backtesting import StrategyVariantsRequest, run_strategy_variants

    with pytest.raises(HTTPException) as exc_info:
        run_strategy_variants(StrategyVariantsRequest(batch_id="does-not-exist"))
    assert exc_info.value.status_code == 404
