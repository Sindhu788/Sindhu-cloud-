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


def test_a_completed_batch_writes_a_backtest_snapshot_for_the_cloud_page(test_db, monkeypatch):
    """Master Task 3, Phase 0.7: this is the write side of the dual-row
    Strategies table -- once this strategy has a completed local batch,
    _compute_strategies_list must persist a snapshot (win_rate,
    profit_factor, ...) into meta.json via strategy_library.
    save_backtest_snapshot, using the exact numbers it already computed for
    the local page (no extra queries)."""
    sid = _make_strategy("Snapshot Source Strategy")

    monkeypatch.setattr(
        backtesting, "_strategy_last_batch_result",
        lambda name, recent_batches, batch_results_cache=None: {
            "batch_id": "batchXYZ", "status": "completed", "created_at": "2026-02-01T00:00:00+00:00",
            "total_trades": 80, "symbols_tested": 10, "win_rate": 57.5, "avg_profit_pct": 3.2,
        },
    )
    monkeypatch.setattr(
        backtesting, "evaluate_strategy_performance",
        lambda strategy_id, recent_batches=None, batch_results_cache=None: {
            "verdict": "GREEN", "label": "Aage Badhao", "failed_factors": [],
            "factors": [{"factor": "profit_factor", "passed": True, "available": True, "value": 1.62}],
            "batch_id": "batchXYZ", "symbols_tested": 10,
        },
    )

    result = backtesting._compute_strategies_list("")
    row = next(r for r in result if r["id"] == sid)
    assert row["last_batch_result"]["win_rate"] == 57.5

    snapshot = lib._read_meta(sid)["backtest_snapshot"]
    assert snapshot == {
        "win_rate": 57.5, "profit_factor": 1.62, "total_trades": 80,
        "batch_id": "batchXYZ", "computed_at": "2026-02-01T00:00:00+00:00",
    }


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
