"""Batch 6, Task 6: optimizer efficiency (coarse-to-fine / early
elimination). Confirms the SAME best candidate is still found as an
exhaustive grid search would find, but with real, provably fewer full
backtest runs (_run_in_memory_bounded calls) -- and that _score() itself
is never touched, only which candidates get scored.

A synthetic dimension with a known, deliberately non-monotonic-then-
monotonic score curve (peaks near the baseline, then strictly worsens
further out in both directions) lets the test assert exactly which
candidates get skipped, without needing a real backtest at all --
automation_pipeline.optimizer._run_in_memory_bounded is monkeypatched to
a pure lookup instead.
"""

import pytest

from automation_pipeline import optimizer
from backtest_engine.strategy_config import StrategyConfig


def _base_config():
    return StrategyConfig(name="Efficiency Test", risk_pct=1.0)


# below (nearest-to-baseline first): 45, 40, 30, 20, 10 -- peaks at 40, then
# strictly worsens through 30 -> 20 -> (10 would be worse still, skipped)
# above (nearest-to-baseline first): 55, 60, 70, 80, 90 -- strictly worsens
# the whole way, so 80/90 should be skipped after 55/60/70 confirm the trend.
_SCORES = {45: 5.0, 40: 10.0, 30: 0.0, 20: -10.0, 10: -20.0,
           55: 2.0, 60: -5.0, 70: -15.0, 80: -25.0, 90: -35.0}


def _synthetic_dim(candidates=(10, 20, 30, 40, 45, 50, 55, 60, 70, 80, 90), baseline=50):
    def _apply(cfg, value):
        cfg._test_value = value
        return cfg
    return {"id": "test_dim", "description": "synthetic test dimension",
            "baseline": baseline, "candidates": list(candidates), "apply": _apply}


@pytest.fixture
def call_log(monkeypatch):
    calls = []

    def _fake_run_in_memory_bounded(config, exchange, symbol, settings, start_ms, end_ms, log):
        value = getattr(config, "_test_value", None)
        calls.append(value)
        score = _SCORES.get(value, 0.0) if value is not None else 0.0
        # enough trades to always be trusted (>= MIN_TRADES_FOR_SCORE)
        return {"total_trades": 10, "profit_pct": score}

    monkeypatch.setattr(optimizer, "_run_in_memory_bounded", _fake_run_in_memory_bounded)
    return calls


def test_early_elimination_skips_candidates_far_from_the_peak_but_finds_the_same_best(monkeypatch, call_log):
    monkeypatch.setattr(optimizer, "tunable_dimensions", lambda cfg: [_synthetic_dim()])
    cfg = _base_config()

    best, tried, best_desc = optimizer.optimize(cfg, "binance", "BTCUSDT", {"initial_balance": 1000.0}, 0, 1)

    # The true global best (peak at 40, score 0.0) is still found, exactly
    # as an exhaustive search would find -- early elimination only skips
    # candidates that are provably further from an already-worsening trend.
    assert best is not None
    assert best_desc == "synthetic test dimension -> 40"

    skipped_values = {t["value"] for t in tried if t.get("skipped")}
    real_values = [v for v in call_log if v is not None]

    # 10 (below, past the 30->20 worsening streak) and 80, 90 (above, past
    # the 55->60->70 worsening streak) must never have been fully backtested.
    assert skipped_values == {10, 80, 90}
    assert 10 not in real_values
    assert 80 not in real_values
    assert 90 not in real_values

    # Every candidate that WASN'T skipped (7 of the 10 non-baseline values,
    # plus the baseline itself) really was backtested -- nothing silently
    # dropped without being logged either as tried or as skipped.
    assert set(real_values) == {45, 40, 30, 20, 55, 60, 70}
    assert len(tried) == 1 + 10  # baseline + all 10 candidates, tried or skipped
    assert sum(1 for t in tried if t.get("skipped")) == 3


def test_exhaustive_search_would_have_needed_three_more_backtests(monkeypatch, call_log):
    """Direct before/after comparison: same dimension, but with early
    elimination disabled (streak threshold raised so it can never trigger)
    -- confirms the saved calls are real, not a test artifact."""
    monkeypatch.setattr(optimizer, "tunable_dimensions", lambda cfg: [_synthetic_dim()])
    monkeypatch.setattr(optimizer, "_EARLY_STOP_WORSENING_STREAK", 999)
    cfg = _base_config()

    best, tried, best_desc = optimizer.optimize(cfg, "binance", "BTCUSDT", {"initial_balance": 1000.0}, 0, 1)
    assert best_desc == "synthetic test dimension -> 40"
    assert sum(1 for t in tried if t.get("skipped")) == 0
    real_values = [v for v in call_log if v is not None]
    assert set(real_values) == {10, 20, 30, 40, 45, 55, 60, 70, 80, 90}  # every candidate really run


def test_non_numeric_dimension_is_never_early_eliminated(monkeypatch, call_log):
    """session_filter-style dimensions (candidates are tuples, not plain
    numbers) have no meaningful 'distance from baseline' -- must always be
    searched exhaustively regardless of how the scores trend."""
    def _apply(cfg, value):
        cfg._test_value = value
        return cfg

    # Deliberately monotonically worsening "distance" order (by list
    # position) to prove skip logic never kicks in for non-numeric values.
    candidates = [("a",), ("b",), ("c",), ("d",), ("e",)]
    dim = {"id": "categorical_dim", "description": "categorical test dimension",
           "baseline": (), "candidates": candidates, "apply": _apply}
    monkeypatch.setattr(optimizer, "tunable_dimensions", lambda cfg: [dim])

    scores_by_tuple = {("a",): -1.0, ("b",): -2.0, ("c",): -3.0, ("d",): -4.0, ("e",): -5.0}

    def _fake_run(config, exchange, symbol, settings, start_ms, end_ms, log):
        value = getattr(config, "_test_value", None)
        call_log.append(value)
        return {"total_trades": 10, "profit_pct": scores_by_tuple.get(value, 0.0)}
    monkeypatch.setattr(optimizer, "_run_in_memory_bounded", _fake_run)

    cfg = _base_config()
    best, tried, best_desc = optimizer.optimize(cfg, "binance", "BTCUSDT", {"initial_balance": 1000.0}, 0, 1)

    assert sum(1 for t in tried if t.get("skipped")) == 0
    assert set(v for v in call_log if v is not None) == set(candidates)


def test_score_function_itself_is_completely_unchanged():
    """Batch 6, Task 6 explicitly requires scoring not to change --
    _score() must still floor at MIN_TRADES_FOR_SCORE and return
    profit_pct otherwise, exactly as before this task."""
    assert optimizer._score(None) == float("-inf")
    assert optimizer._score({"total_trades": optimizer.MIN_TRADES_FOR_SCORE - 1, "profit_pct": 999}) == float("-inf")
    assert optimizer._score({"total_trades": optimizer.MIN_TRADES_FOR_SCORE, "profit_pct": 12.5}) == 12.5
