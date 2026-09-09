"""Urgent bug fix, 2026-09-09: three separate call sites --
paper_trading.capital_allocation.recompute_all_allocations() (every tick,
when the feature is on), .compute_all_risk_pct_recommendations(), and
paper_trading.portfolio.compute_portfolio_risk_score() -- each looped
insights.compute_risk_metrics() once per strategy, and each opens its own
fresh Postgres connection (no pooling on the cloud runner). Two of these
loop over literally every LIBRARY strategy (~154), regardless of whether
it's even enabled -- the same class of bug already fixed for decisions/
analytics/status, just hiding in three more places. Fixed by
insights.compute_risk_metrics_batch(), one shared query for any number of
strategy_ids, and this file confirms it returns identical numbers to
calling compute_risk_metrics() once per id, plus the actual connection
count for each of the three fixed call sites.
"""
from datetime import datetime, timezone, timedelta

import pytest

from data_engine import config as base_config, storage
from backtest_engine import strategy_library as lib
from backtest_engine.strategy_config import Condition, SLTPSpec, StrategyConfig
from paper_trading import capital_allocation, insights, portfolio


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


@pytest.fixture(autouse=True)
def isolated_library(tmp_path, monkeypatch):
    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path / "library"))


def _config(name):
    return StrategyConfig(
        name=name, timeframes={"entry": "5m"},
        entry_conditions=[Condition(type="indicator_compare", indicator="rsi", op="<", value=30)],
        exit_conditions=[Condition(type="indicator_compare", indicator="macd", op=">", value=0)],
        concepts_used=["resistance"],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0), take_profit=SLTPSpec(type="rr", value=2.5),
        risk_pct=1.0, risk_reward=2.5,
    )


def _close(position_id, pnl, strategy_id, days_ago=0):
    pos = {
        "id": position_id, "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": 1700000000000,
        "created_at": (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(),
        "strategy_id": strategy_id, "strategy_name": strategy_id,
    }
    storage.open_paper_position(pos)
    storage.close_paper_position(
        position_id, 100.0 + pnl, 1700000100000, pnl, pnl,
        "take_profit" if pnl >= 0 else "stop_loss", {}, {},
        (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(),
    )


def _counting_get_conn(monkeypatch):
    call_count = {"n": 0}
    real_get_conn = storage.get_conn

    def counting():
        call_count["n"] += 1
        return real_get_conn()

    monkeypatch.setattr(storage, "get_conn", counting)
    return call_count


def test_batch_matches_single_strategy_calls(test_db):
    for i, pnl in enumerate([10.0, -5.0, 8.0, -3.0, 12.0]):
        _close(f"a{i}", pnl, "strat_a", days_ago=i)
    for i, pnl in enumerate([50.0, 60.0, -2.0]):
        _close(f"b{i}", pnl, "strat_b", days_ago=i)

    individually = {
        "strat_a": insights.compute_risk_metrics("strat_a"),
        "strat_b": insights.compute_risk_metrics("strat_b"),
        "strat_c": insights.compute_risk_metrics("strat_c"),  # no trades at all
    }
    batched = insights.compute_risk_metrics_batch(["strat_a", "strat_b", "strat_c"])

    assert batched == individually


def test_batch_uses_one_connection_for_many_strategies(test_db, monkeypatch):
    for i, pnl in enumerate([10.0, -5.0, 8.0]):
        _close(f"a{i}", pnl, "strat_a", days_ago=i)

    call_count = _counting_get_conn(monkeypatch)
    insights.compute_risk_metrics_batch([f"strat{i}" for i in range(50)] + ["strat_a"])

    assert call_count["n"] == 1


def test_empty_id_list_opens_no_connection(test_db, monkeypatch):
    call_count = _counting_get_conn(monkeypatch)
    result = insights.compute_risk_metrics_batch([])
    assert result == {}
    assert call_count["n"] == 0


def test_recompute_all_allocations_stays_low_on_connections_at_scale(test_db, monkeypatch):
    for i in range(40):
        lib.create(_config(f"Strategy {i}"))

    call_count = _counting_get_conn(monkeypatch)
    capital_allocation.recompute_all_allocations()

    # Before this fix: one connection per library strategy (40+). Now: a
    # small constant regardless of strategy count.
    assert call_count["n"] < 5


def test_risk_pct_recommendations_stays_low_on_connections_at_scale(test_db, monkeypatch):
    for i in range(40):
        lib.create(_config(f"Strategy {i}"))

    call_count = _counting_get_conn(monkeypatch)
    capital_allocation.compute_all_risk_pct_recommendations(1.0)

    assert call_count["n"] < 5


def test_portfolio_risk_score_stays_low_on_connections_at_scale(test_db, monkeypatch):
    strategy_ids = [f"strat{i}" for i in range(75)]
    call_count = _counting_get_conn(monkeypatch)
    portfolio.compute_portfolio_risk_score(strategy_ids)

    assert call_count["n"] < 5
