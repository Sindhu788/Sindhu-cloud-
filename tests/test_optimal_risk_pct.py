"""Grand Feature Expansion, Phase 5 Feature 6: Optimal Risk % Per Strategy
(paper_trading/capital_allocation.py's compute_recommended_risk_pct /
compute_all_risk_pct_recommendations) -- reuses the exact same bounded,
transparent Sharpe-driven formula shape as the existing capital multiplier,
just applied to risk_pct specifically. Suggestion only: applying one goes
through the EXISTING per-strategy override endpoint, never a new one.
"""

import pytest

from backtest_engine import strategy_library as lib
from backtest_engine.strategy_config import Condition, SLTPSpec, StrategyConfig
from data_engine import config as base_config
from paper_trading import capital_allocation, insights


@pytest.fixture(autouse=True)
def isolated_library(tmp_path, monkeypatch):
    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path / "lib"))
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _config(name):
    return StrategyConfig(
        name=name,
        timeframes={"entry": "1m"},
        indicators=[{"name": "sma", "params": {"period": 3}, "role": "entry"}],
        entry_conditions=[
            Condition(type="price_compare", op=">", indicator="sma", params={"period": 3}),
        ],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0),
        take_profit=SLTPSpec(type="fixed_pct", value=2.0),
        risk_pct=1.0,
    )


def test_compute_recommended_risk_pct_matches_the_multiplier_formula():
    # Sharpe of 0 keeps the multiplier at 1.0 -- same baseline convention
    # as compute_multiplier itself.
    assert capital_allocation.compute_recommended_risk_pct(1.0, 0.0) == 1.0
    assert capital_allocation.compute_recommended_risk_pct(1.0, 2.0) == pytest.approx(1.2)
    assert capital_allocation.compute_recommended_risk_pct(1.0, -2.0) == pytest.approx(0.8)


def test_recommended_risk_pct_respects_the_same_bounds_as_the_multiplier():
    # An extreme Sharpe still can't push the swing past +/-50%.
    assert capital_allocation.compute_recommended_risk_pct(1.0, 100.0) == pytest.approx(1.5)
    assert capital_allocation.compute_recommended_risk_pct(1.0, -100.0) == pytest.approx(0.5)


def test_too_little_data_produces_no_recommendation(test_db, monkeypatch):
    sid = lib.create(_config("Fresh Strategy"))
    monkeypatch.setattr(insights, "compute_risk_metrics", lambda *a, **k: {"sharpe_ratio": 2.0, "sample_size": 2})
    recs = capital_allocation.compute_all_risk_pct_recommendations(1.0)
    assert recs == []


def test_a_strong_sharpe_produces_an_increase_recommendation(test_db, monkeypatch):
    sid = lib.create(_config("Strong Strategy"))
    monkeypatch.setattr(insights, "compute_risk_metrics", lambda *a, **k: {"sharpe_ratio": 2.0, "sample_size": 10})
    recs = capital_allocation.compute_all_risk_pct_recommendations(1.0)
    assert len(recs) == 1
    assert recs[0]["strategy_id"] == sid
    assert recs[0]["current_risk_pct"] == 1.0
    assert recs[0]["recommended_risk_pct"] == pytest.approx(1.2)
    assert "increase" in recs[0]["reason"]


def test_a_weak_sharpe_produces_a_decrease_recommendation(test_db, monkeypatch):
    lib.create(_config("Weak Strategy"))
    monkeypatch.setattr(insights, "compute_risk_metrics", lambda *a, **k: {"sharpe_ratio": -2.0, "sample_size": 10})
    recs = capital_allocation.compute_all_risk_pct_recommendations(1.0)
    assert len(recs) == 1
    assert recs[0]["recommended_risk_pct"] == pytest.approx(0.8)
    assert "decrease" in recs[0]["reason"]


def test_a_near_zero_sharpe_produces_no_recommendation(test_db, monkeypatch):
    lib.create(_config("Average Strategy"))
    monkeypatch.setattr(insights, "compute_risk_metrics", lambda *a, **k: {"sharpe_ratio": 0.01, "sample_size": 10})
    recs = capital_allocation.compute_all_risk_pct_recommendations(1.0)
    assert recs == []


def test_endpoint_returns_recommendations(test_db, monkeypatch):
    from sindhu_web.api.paper_trading import get_risk_pct_recommendations

    lib.create(_config("Strong Strategy"))
    monkeypatch.setattr(insights, "compute_risk_metrics", lambda *a, **k: {"sharpe_ratio": 2.0, "sample_size": 10})
    result = get_risk_pct_recommendations()
    assert len(result["recommendations"]) == 1
