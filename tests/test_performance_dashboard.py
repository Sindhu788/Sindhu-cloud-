"""Strategy Performance Dashboard (backtest_engine/performance_dashboard.py):
a pure read-only combiner over 4 already-computed factors. These tests
verify: each factor's individual pass/fail boundary, the "no data yet"
state is distinct from "failed" but still counts toward RED, and the
overall verdict/label logic -- using monkeypatched storage/strategy_library
so nothing here touches a real database or runs a real backtest (the real
end-to-end evidence is scripts/run_walk_forward_demo.py's already-produced
data plus a live check against the actual API, not a unit test).
"""

import pytest

from backtest_engine import performance_dashboard as pd


def _pooled(trades=200, expectancy=5.0, profit_factor=1.5):
    total_pnl = expectancy * trades if expectancy is not None and trades else None
    return {
        "batch_id": "batch123", "symbols_tested": 2, "total_trades": trades,
        "total_pnl": total_pnl, "expectancy": expectancy, "profit_factor": profit_factor,
    }


# ------------------------------------------------------------ individual factor checks

def test_expectancy_passes_when_positive():
    r = pd._check_expectancy(_pooled(expectancy=1.0))
    assert r["passed"] is True and r["available"] is True


def test_expectancy_fails_when_negative():
    r = pd._check_expectancy(_pooled(expectancy=-0.01))
    assert r["passed"] is False and r["available"] is True


def test_expectancy_fails_when_exactly_zero():
    r = pd._check_expectancy(_pooled(expectancy=0.0))
    assert r["passed"] is False


def test_expectancy_not_available_with_no_batch():
    r = pd._check_expectancy(None)
    assert r["passed"] is False and r["available"] is False


def test_profit_factor_passes_at_threshold():
    r = pd._check_profit_factor(_pooled(profit_factor=1.3))
    assert r["passed"] is True


def test_profit_factor_fails_just_below_threshold():
    r = pd._check_profit_factor(_pooled(profit_factor=1.2999))
    assert r["passed"] is False


def test_trade_count_passes_at_threshold():
    r = pd._check_trade_count(_pooled(trades=100))
    assert r["passed"] is True


def test_trade_count_fails_below_threshold():
    r = pd._check_trade_count(_pooled(trades=99))
    assert r["passed"] is False
    assert "99 trades" in r["detail"]


def test_walk_forward_passes_on_pass_status():
    r = pd._check_walk_forward({"walk_forward_status": "PASS", "walk_forward_result": {"reason": "ok"}})
    assert r["passed"] is True


def test_walk_forward_fails_on_fail_status_with_real_reason_surfaced():
    r = pd._check_walk_forward({
        "walk_forward_status": "FAIL",
        "walk_forward_result": {"reason": "Not profitable even in the training period (-24.88% return)."},
    })
    assert r["passed"] is False
    assert "-24.88%" in r["detail"]


def test_walk_forward_not_available_when_never_run():
    r = pd._check_walk_forward({})
    assert r["passed"] is False and r["available"] is False
    assert "not been run" in r["detail"]


# ------------------------------------------------------------ evaluate_strategy_performance (orchestration)

class _FakeConfig:
    name = "Fake Strategy"


def test_evaluate_returns_green_when_all_four_factors_pass(monkeypatch):
    monkeypatch.setattr(pd.strategy_library, "load", lambda sid: _FakeConfig())
    monkeypatch.setattr(pd.strategy_library, "_read_meta",
                         lambda sid: {"walk_forward_status": "PASS", "walk_forward_result": {"reason": "held up"}})
    monkeypatch.setattr(pd, "find_last_completed_batch", lambda name, recent_batches=None: {"batch_id": "b1"})
    monkeypatch.setattr(pd, "_pooled_batch_metrics",
                         lambda batch, batch_results_cache=None: _pooled(trades=150, expectancy=2.0, profit_factor=1.8))

    result = pd.evaluate_strategy_performance("fake-id")
    assert result["verdict"] == "GREEN"
    assert result["label"] == "Aage Badhao"
    assert result["failed_factors"] == []
    assert all(f["passed"] for f in result["factors"])


def test_evaluate_returns_red_with_specific_named_failures(monkeypatch):
    monkeypatch.setattr(pd.strategy_library, "load", lambda sid: _FakeConfig())
    monkeypatch.setattr(pd.strategy_library, "_read_meta",
                         lambda sid: {"walk_forward_status": "FAIL", "walk_forward_result": {"reason": "overfit"}})
    monkeypatch.setattr(pd, "find_last_completed_batch", lambda name, recent_batches=None: {"batch_id": "b1"})
    # Passes trade count and expectancy, but profit factor and walk-forward fail.
    monkeypatch.setattr(pd, "_pooled_batch_metrics",
                         lambda batch, batch_results_cache=None: _pooled(trades=546, expectancy=0.5, profit_factor=0.9))

    result = pd.evaluate_strategy_performance("fake-id")
    assert result["verdict"] == "RED"
    assert result["label"] == "Abhi Ready Nahi"
    assert len(result["failed_factors"]) == 2  # profit_factor + walk_forward only
    assert any("Profit Factor" in f for f in result["failed_factors"])
    assert any("Walk-Forward" in f for f in result["failed_factors"])
    assert not any("Trade Count" in f for f in result["failed_factors"])
    assert not any("Expectancy" in f for f in result["failed_factors"])


def test_evaluate_red_when_no_backtest_has_ever_run(monkeypatch):
    monkeypatch.setattr(pd.strategy_library, "load", lambda sid: _FakeConfig())
    monkeypatch.setattr(pd.strategy_library, "_read_meta", lambda sid: {})
    monkeypatch.setattr(pd, "find_last_completed_batch", lambda name, recent_batches=None: None)

    result = pd.evaluate_strategy_performance("fake-id")
    assert result["verdict"] == "RED"
    assert result["batch_id"] is None
    assert len(result["failed_factors"]) == 4  # all four factors unavailable/failed
    assert all("not available yet" in f or "Walk-Forward" in f for f in result["failed_factors"])


def test_evaluate_returns_none_for_a_deleted_or_missing_strategy(monkeypatch):
    def _raise(sid):
        raise FileNotFoundError()
    monkeypatch.setattr(pd.strategy_library, "load", _raise)
    assert pd.evaluate_strategy_performance("does-not-exist") is None


# ------------------------------------------------------------ _pooled_batch_metrics (real pooling math)

def test_pooled_metrics_expectancy_is_dollar_weighted_not_averaged(monkeypatch):
    """Two symbols: one with 10 trades losing a lot, one with 990 trades
    barely profitable. A naive average-of-per-symbol-expectancy would be
    dominated by the small sample; the pooled (total $ / total trades)
    figure must reflect the REAL, trade-weighted outcome instead."""
    batch = {"batch_id": "b1", "settings": {"initial_balance": 1000.0}}
    fake_results = [
        {"status": "completed", "metrics": {"total_trades": 10, "final_balance": 500.0, "profit_factor": 0.2}},
        {"status": "completed", "metrics": {"total_trades": 990, "final_balance": 1100.0, "profit_factor": 1.1}},
    ]
    monkeypatch.setattr(pd.storage, "get_batch_results", lambda batch_id: fake_results)

    result = pd._pooled_batch_metrics(batch)
    assert result["total_trades"] == 1000
    # total_pnl = (500-1000) + (1100-1000) = -500 + 100 = -400; expectancy = -400/1000 = -0.4
    assert result["total_pnl"] == -400.0
    assert result["expectancy"] == -0.4
