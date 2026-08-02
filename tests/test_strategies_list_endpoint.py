"""Batch 4, Task 1 -- the dashboard performance fix added a short-TTL cache
in front of GET /api/backtesting/strategies (sindhu_web.api.backtesting.
list_strategies), plus per-request deduplication of the duplicate
get_batch_results() call made by _strategy_last_batch_result and
evaluate_strategy_performance for the same batch.

A refactor of that endpoint accidentally double-wrapped the response as
{"strategies": {"strategies": [...]}}, only caught by loading the real page
in a browser (no existing test asserted the response shape). These tests
close that gap.
"""

import pytest

from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from backtest_engine import strategy_library as lib
from sindhu_web import cache
from sindhu_web.api import backtesting


@pytest.fixture(autouse=True)
def isolated_library(tmp_path, monkeypatch):
    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path / "library"))
    cache.invalidate(backtesting._STRATEGIES_CACHE_KEY)
    yield
    cache.invalidate(backtesting._STRATEGIES_CACHE_KEY)


def _make_strategy(name="Test Strategy"):
    cfg = StrategyConfig(
        name=name, timeframes={"entry": "1h"},
        entry_conditions=[Condition(type="indicator_compare", indicator="rsi", op="<", value=30.0)],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0), take_profit=SLTPSpec(type="fixed_pct", value=2.0),
        risk_pct=1.0,
    )
    return lib.create(cfg)


def test_response_shape_is_a_flat_list_not_double_wrapped(test_db):
    _make_strategy()
    result = backtesting.list_strategies(q="")
    assert isinstance(result, dict)
    assert isinstance(result["strategies"], list)
    assert len(result["strategies"]) == 1
    assert "strategies" not in result["strategies"][0]  # not double-wrapped


def test_search_query_bypasses_the_cache_and_stays_a_flat_list(test_db):
    _make_strategy("Findable Strategy")
    result = backtesting.list_strategies(q="Findable")
    assert isinstance(result["strategies"], list)
    assert result["strategies"][0]["name"] == "Findable Strategy"


def test_repeated_calls_within_ttl_return_the_same_cached_list(test_db):
    _make_strategy()
    first = backtesting.list_strategies(q="")
    second = backtesting.list_strategies(q="")
    assert first == second
    assert len(first["strategies"]) == 1


def test_saving_a_strategy_invalidates_the_cache_immediately(test_db):
    backtesting.list_strategies(q="")  # warm the cache with zero strategies
    req = backtesting.SaveRequest(config=StrategyConfig(
        name="New After Cache Warm", timeframes={"entry": "1h"},
        entry_conditions=[Condition(type="indicator_compare", indicator="rsi", op="<", value=30.0)],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0), take_profit=SLTPSpec(type="fixed_pct", value=2.0),
        risk_pct=1.0,
    ).to_dict())
    backtesting.save_strategy(req)
    result = backtesting.list_strategies(q="")
    assert len(result["strategies"]) == 1
    assert result["strategies"][0]["name"] == "New After Cache Warm"
