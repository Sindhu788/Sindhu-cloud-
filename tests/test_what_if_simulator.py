"""Grand Feature Expansion, Phase 5 Feature 14: Historical What-If
Simulator (backtest_engine/what_if_simulator.py) -- a genuine counterfactual
RE-SIMULATION ("what if this parameter had been different"), distinct from
Monte Carlo (reshuffles already-recorded PnL, no re-simulation) and
Challenge Mode's own "What-If" (filters real combos, never changes a
historical parameter). Reuses automation_pipeline.optimizer._run_in_memory
exactly as walk_forward.py already does -- tests here monkeypatch it so
they don't depend on real market data or real backtest time, same pattern
as tests/test_walk_forward.py.
"""

import pytest

from backtest_engine import what_if_simulator
from backtest_engine.strategy_config import Condition, SLTPSpec, StrategyConfig


def _config(risk_pct=1.0, sl_value=1.0):
    return StrategyConfig(
        name="Test Strategy",
        timeframes={"entry": "1m"},
        indicators=[{"name": "sma", "params": {"period": 3}, "role": "entry"}],
        entry_conditions=[
            Condition(type="price_compare", op=">", indicator="sma", params={"period": 3}),
        ],
        stop_loss=SLTPSpec(type="fixed_pct", value=sl_value),
        take_profit=SLTPSpec(type="fixed_pct", value=2.0),
        risk_pct=risk_pct,
    )


def _batch(symbols=None, start_ms=0, end_ms=90 * 24 * 3600 * 1000):
    return {
        "exchange": "binance",
        "settings": {
            "initial_balance": 10000.0,
            "symbols": symbols if symbols is not None else ["BTCUSDT", "ETHUSDT"],
            "start_ms": start_ms, "end_ms": end_ms,
        },
    }


def test_apply_parameter_changes_clones_and_never_mutates_the_original():
    original = _config(risk_pct=1.0)
    modified = what_if_simulator._apply_parameter_changes(original, {"risk_pct": 2.0})
    assert original.risk_pct == 1.0
    assert modified.risk_pct == 2.0


def test_apply_parameter_changes_reconstructs_sltp_spec_from_a_dict():
    original = _config(sl_value=1.0)
    modified = what_if_simulator._apply_parameter_changes(
        original, {"stop_loss": {"type": "fixed_pct", "value": 2.0}})
    assert original.stop_loss.value == 1.0
    assert modified.stop_loss.value == 2.0
    assert modified.stop_loss.type == "fixed_pct"


def test_returns_none_when_batch_has_no_symbols_or_date_range():
    cfg = _config()
    batch = _batch(symbols=[])
    assert what_if_simulator.run_what_if(cfg, batch, {"risk_pct": 2.0}) is None


def test_windows_to_the_last_30_days_of_a_longer_range(monkeypatch):
    cfg = _config()
    batch = _batch(start_ms=0, end_ms=90 * 24 * 3600 * 1000)
    captured_starts = []

    def fake_run_in_memory(config, exchange, symbol, settings, start_ms, end_ms):
        captured_starts.append(start_ms)
        return {"total_trades": 1, "net_profit": 10.0}

    monkeypatch.setattr(what_if_simulator.optimizer, "_run_in_memory", fake_run_in_memory)
    result = what_if_simulator.run_what_if(cfg, batch, {"risk_pct": 2.0})
    expected_start = batch["settings"]["end_ms"] - what_if_simulator.FAST_WINDOW_DAYS * 24 * 3600 * 1000
    assert all(s == expected_start for s in captured_starts)
    assert result["window_days"] == 30


def test_caps_symbols_at_max_symbols(monkeypatch):
    cfg = _config()
    batch = _batch(symbols=["A", "B", "C", "D", "E", "F", "G"])
    monkeypatch.setattr(what_if_simulator.optimizer, "_run_in_memory",
                         lambda *a, **k: {"total_trades": 1, "net_profit": 5.0})
    result = what_if_simulator.run_what_if(cfg, batch, {"risk_pct": 2.0}, max_symbols=3)
    assert len(result["symbols"]) == 3


def test_aggregates_original_vs_modified_across_symbols(monkeypatch):
    cfg = _config()
    batch = _batch(symbols=["BTCUSDT", "ETHUSDT"])

    def fake_run_in_memory(config, exchange, symbol, settings, start_ms, end_ms):
        # The modified config (risk_pct=2.0) does noticeably better.
        if config.risk_pct == 2.0:
            return {"total_trades": 10, "net_profit": 200.0}
        return {"total_trades": 10, "net_profit": 100.0}

    monkeypatch.setattr(what_if_simulator.optimizer, "_run_in_memory", fake_run_in_memory)
    result = what_if_simulator.run_what_if(cfg, batch, {"risk_pct": 2.0})
    assert result["original"]["net_profit"] == pytest.approx(200.0)   # 100 * 2 symbols
    assert result["modified"]["net_profit"] == pytest.approx(400.0)   # 200 * 2 symbols
    assert result["parameter_changes"] == {"risk_pct": 2.0}


def test_handles_a_symbol_with_no_usable_data(monkeypatch):
    cfg = _config()
    batch = _batch(symbols=["BTCUSDT"])
    monkeypatch.setattr(what_if_simulator.optimizer, "_run_in_memory", lambda *a, **k: None)
    result = what_if_simulator.run_what_if(cfg, batch, {"risk_pct": 2.0})
    assert result["original"]["total_trades"] == 0
    assert result["modified"]["net_profit"] == 0.0


def test_endpoint_runs_a_what_if(test_db, monkeypatch, tmp_path):
    from backtest_engine import strategy_library as lib
    from sindhu_web.api.backtesting import WhatIfRequest, run_what_if_simulation

    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path))
    lib.create(_config())  # name matches batch["strategy_name"] below
    from data_engine import storage
    now_iso = "2026-01-01T00:00:00+00:00"
    storage.create_batch("batch1", "Test Strategy", "binance",
                          {"initial_balance": 10000.0, "symbols": ["BTCUSDT"], "start_ms": 0, "end_ms": 90 * 24 * 3600 * 1000},
                          now_iso)
    monkeypatch.setattr(what_if_simulator.optimizer, "_run_in_memory",
                         lambda *a, **k: {"total_trades": 1, "net_profit": 5.0})
    result = run_what_if_simulation(WhatIfRequest(batch_id="batch1", parameter_changes={"risk_pct": 2.0}))
    assert result["modified"]["total_trades"] == 1


def test_endpoint_404s_for_unknown_batch(test_db):
    from fastapi import HTTPException
    from sindhu_web.api.backtesting import WhatIfRequest, run_what_if_simulation

    with pytest.raises(HTTPException) as exc_info:
        run_what_if_simulation(WhatIfRequest(batch_id="does-not-exist", parameter_changes={}))
    assert exc_info.value.status_code == 404


def test_endpoint_404s_when_strategy_no_longer_exists(test_db, tmp_path, monkeypatch):
    from backtest_engine import strategy_library as lib
    from data_engine import storage
    from fastapi import HTTPException
    from sindhu_web.api.backtesting import WhatIfRequest, run_what_if_simulation

    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path))
    storage.create_batch("batch2", "Deleted Strategy", "binance",
                          {"initial_balance": 10000.0, "symbols": ["BTCUSDT"], "start_ms": 0, "end_ms": 1000},
                          "2026-01-01T00:00:00+00:00")
    with pytest.raises(HTTPException) as exc_info:
        run_what_if_simulation(WhatIfRequest(batch_id="batch2", parameter_changes={}))
    assert exc_info.value.status_code == 404
