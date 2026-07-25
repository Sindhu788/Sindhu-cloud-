"""Walk-Forward Testing (automation_pipeline/walk_forward.py): checks
whether a strategy's parameters are genuinely robust or just overfit to
the data they were tuned on. Tests cover the two independently-verifiable
pieces:
  1. compute_split() -- the chronological (never shuffled) 70/30 boundary,
     against real stored time bounds.
  2. _verdict() -- the disclosed PASS/FAIL/INCONCLUSIVE decision rule,
     covering every branch (too few trades, unprofitable training,
     profitable-in-training-but-loses-in-testing, and the WFE threshold
     itself on both sides of the line).
Plus one integration test proving run_walk_forward_test() wires
optimizer.optimize() + _run_in_memory() together correctly end-to-end,
using a monkeypatched optimizer so it doesn't depend on real market data
or take real backtest time -- the REAL end-to-end run against an actual
saved strategy is scripts/run_walk_forward_demo.py, not a unit test.
"""

import pytest

from automation_pipeline import walk_forward


# ------------------------------------------------------------ compute_split

def test_compute_split_is_chronological_70_30(monkeypatch):
    from automation_pipeline import walk_forward as wf_mod

    monkeypatch.setattr(wf_mod.storage, "get_symbol_time_bounds", lambda ex, sym: (0, 1_000_000))
    split = wf_mod.compute_split("binance", "BTCUSDT")
    assert split["train_start_ms"] == 0
    assert split["train_end_ms"] == 700_000
    assert split["test_start_ms"] == 700_000
    assert split["test_end_ms"] == 1_000_000
    # No gap and no overlap -- train ends exactly where test begins.
    assert split["train_end_ms"] == split["test_start_ms"]


def test_compute_split_honors_a_custom_train_fraction(monkeypatch):
    from automation_pipeline import walk_forward as wf_mod

    monkeypatch.setattr(wf_mod.storage, "get_symbol_time_bounds", lambda ex, sym: (0, 1_000_000))
    split = wf_mod.compute_split("binance", "BTCUSDT", train_fraction=0.5)
    assert split["train_end_ms"] == 500_000


def test_compute_split_returns_none_when_no_data_exists(monkeypatch):
    from automation_pipeline import walk_forward as wf_mod

    monkeypatch.setattr(wf_mod.storage, "get_symbol_time_bounds", lambda ex, sym: (None, None))
    assert wf_mod.compute_split("binance", "NOPE") is None


# ------------------------------------------------------------ _verdict

def _metrics(trades, profit_pct):
    return {"total_trades": trades, "win_rate": 50.0, "profit_pct": profit_pct,
            "net_profit": profit_pct * 10, "profit_factor": 1.5, "max_drawdown_pct": 5.0}


def test_verdict_inconclusive_when_a_period_has_no_metrics():
    status, _ = walk_forward._verdict(None, _metrics(10, 5.0))
    assert status == "INCONCLUSIVE"


def test_verdict_inconclusive_on_too_few_trades():
    status, reason = walk_forward._verdict(_metrics(1, 10.0), _metrics(10, 8.0))
    assert status == "INCONCLUSIVE"
    assert "Too few trades" in reason


def test_verdict_fail_when_training_itself_unprofitable():
    status, reason = walk_forward._verdict(_metrics(10, -5.0), _metrics(10, 2.0))
    assert status == "FAIL"
    assert "training period" in reason.lower()


def test_verdict_fail_on_classic_overfitting_profitable_train_losing_test():
    status, reason = walk_forward._verdict(_metrics(10, 20.0), _metrics(10, -3.0))
    assert status == "FAIL"
    assert "overfitting" in reason.lower()


def test_verdict_pass_when_testing_retains_most_of_training_return():
    """Testing keeps 80% of training's return -- comfortably above the
    50% bar."""
    status, reason = walk_forward._verdict(_metrics(10, 20.0), _metrics(10, 16.0))
    assert status == "PASS"
    assert "80%" in reason


def test_verdict_fail_when_testing_drops_below_the_wfe_threshold():
    """Testing keeps only 20% of training's return -- below the 50% bar."""
    status, reason = walk_forward._verdict(_metrics(10, 20.0), _metrics(10, 4.0))
    assert status == "FAIL"
    assert "20%" in reason


def test_verdict_pass_at_exactly_the_threshold_boundary():
    """Exactly 50% retained -- the threshold is inclusive (>=)."""
    status, _ = walk_forward._verdict(_metrics(10, 20.0), _metrics(10, 10.0))
    assert status == "PASS"


# ------------------------------------------------------------ run_walk_forward_test (integration, mocked)

def test_run_walk_forward_test_wires_optimize_and_scoring_together(monkeypatch):
    from automation_pipeline import walk_forward as wf_mod
    from backtest_engine.strategy_config import StrategyConfig

    monkeypatch.setattr(wf_mod.storage, "get_symbol_time_bounds", lambda ex, sym: (0, 1_000_000))

    cfg = StrategyConfig(name="WF Test Strategy", risk_pct=1.0)
    optimized_cfg = StrategyConfig(name="WF Test Strategy (optimized)", risk_pct=1.5)

    calls = {"optimize_range": None, "scored_ranges": []}

    def fake_optimize(config, exchange, symbol, settings, start_ms, end_ms, log_fn=None, control=None, progress_cb=None):
        calls["optimize_range"] = (start_ms, end_ms)
        return optimized_cfg, [{"dimension": "baseline"}], "risk_pct -> 1.5"

    def fake_run_in_memory(config, exchange, symbol, settings, start_ms, end_ms):
        calls["scored_ranges"].append((start_ms, end_ms, config is optimized_cfg))
        # training period (0-700000): strong profit; testing (700000-1000000): weaker but still positive
        if end_ms <= 700_000:
            return {"total_trades": 20, "win_rate": 55.0, "profit_pct": 30.0, "net_profit": 300.0,
                    "profit_factor": 1.8, "max_drawdown_pct": 8.0}
        return {"total_trades": 12, "win_rate": 50.0, "profit_pct": 18.0, "net_profit": 180.0,
                "profit_factor": 1.4, "max_drawdown_pct": 10.0}

    monkeypatch.setattr(wf_mod.optimizer, "optimize", fake_optimize)
    monkeypatch.setattr(wf_mod.optimizer, "_run_in_memory", fake_run_in_memory)

    settings = {"initial_balance": 1000.0, "risk_pct": 1.0, "commission_pct": 0.1,
                "slippage_pct": 0.05, "position_size_pct": 10.0}
    result = wf_mod.run_walk_forward_test(cfg, "binance", "BTCUSDT", settings)

    # optimize() was called with the TRAINING range only, never the testing range.
    assert calls["optimize_range"] == (0, 700_000)
    # both periods were scored using the OPTIMIZED (winning) config, not the original.
    assert all(used_optimized for _, _, used_optimized in calls["scored_ranges"])
    assert set((s, e) for s, e, _ in calls["scored_ranges"]) == {(0, 700_000), (700_000, 1_000_000)}

    assert result["status"] == "PASS"
    assert result["optimized_params"] == "risk_pct -> 1.5"
    assert result["training_metrics"]["profit_pct"] == 30.0
    assert result["testing_metrics"]["profit_pct"] == 18.0
    assert result["train_period"]["start"] is not None
    assert result["test_period"]["end"] is not None


def test_run_walk_forward_test_falls_back_to_original_config_when_optimizer_finds_nothing_better(monkeypatch):
    from automation_pipeline import walk_forward as wf_mod
    from backtest_engine.strategy_config import StrategyConfig

    monkeypatch.setattr(wf_mod.storage, "get_symbol_time_bounds", lambda ex, sym: (0, 1_000_000))
    cfg = StrategyConfig(name="Original Only", risk_pct=1.0)

    monkeypatch.setattr(wf_mod.optimizer, "optimize",
                         lambda *a, **k: (None, [], None))

    used_configs = []

    def fake_run_in_memory(config, exchange, symbol, settings, start_ms, end_ms):
        used_configs.append(config)
        return {"total_trades": 5, "win_rate": 40.0, "profit_pct": 5.0, "net_profit": 50.0,
                "profit_factor": 1.1, "max_drawdown_pct": 3.0}

    monkeypatch.setattr(wf_mod.optimizer, "_run_in_memory", fake_run_in_memory)

    settings = {"initial_balance": 1000.0, "risk_pct": 1.0, "commission_pct": 0.1,
                "slippage_pct": 0.05, "position_size_pct": 10.0}
    result = wf_mod.run_walk_forward_test(cfg, "binance", "BTCUSDT", settings)

    assert all(c is cfg for c in used_configs)  # scored with the ORIGINAL config, not a phantom optimized one
    assert result["optimized_params"] is None


def test_run_walk_forward_test_returns_error_status_when_no_data_exists(monkeypatch):
    from automation_pipeline import walk_forward as wf_mod
    from backtest_engine.strategy_config import StrategyConfig

    monkeypatch.setattr(wf_mod.storage, "get_symbol_time_bounds", lambda ex, sym: (None, None))
    cfg = StrategyConfig(name="No Data Test")
    result = wf_mod.run_walk_forward_test(cfg, "binance", "NOPE", {"initial_balance": 1000.0})
    assert result["status"] == "ERROR"
