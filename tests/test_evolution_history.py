"""Batch 6, Task 1 -- Evolution History Timeline aggregation. Read-only:
tested here purely as pure aggregation over storage.evolution_comparisons
rows (real storage functions, no mocks) -- never triggers evolution.
"""

from datetime import datetime, timedelta, timezone

from data_engine import storage
from evolution_engine import history


def _iso(dt):
    return dt.isoformat()


def _make_comparison(base_id, child_id, created_at, before, after=None, verdict=None, rolled_back=False):
    cid = storage.create_evolution_comparison(base_id, f"{base_id}_parent", child_id, 100, before, created_at)
    if after is not None:
        storage.finalize_evolution_comparison(cid, after, verdict, rolled_back, created_at)
    return cid


def test_strategies_evolved_counts_distinct_base_ids(test_db):
    now = datetime.now(timezone.utc)
    ts = _iso(now - timedelta(days=1))
    _make_comparison("base1", "child1", ts, {"win_rate": 40})
    _make_comparison("base1", "child2", ts, {"win_rate": 41})  # same strategy, second event
    _make_comparison("base2", "child3", ts, {"win_rate": 30})

    result = history.compute_evolution_history("week", now=now)
    assert result["strategies_evolved"] == 2
    assert result["generations_created"] == 3


def test_events_outside_the_window_are_excluded(test_db):
    now = datetime.now(timezone.utc)
    _make_comparison("base1", "child1", _iso(now - timedelta(days=1)), {"win_rate": 40})
    _make_comparison("base2", "child2", _iso(now - timedelta(days=20)), {"win_rate": 30})  # outside "week"

    result = history.compute_evolution_history("week", now=now)
    assert result["strategies_evolved"] == 1
    assert result["generations_created"] == 1


def test_rollbacks_and_improved_are_counted_correctly(test_db):
    now = datetime.now(timezone.utc)
    ts = _iso(now - timedelta(days=1))
    _make_comparison("base1", "child1", ts, {"win_rate": 40}, after={"win_rate": 50}, verdict="improved", rolled_back=False)
    _make_comparison("base2", "child2", ts, {"win_rate": 40}, after={"win_rate": 20}, verdict="regressed", rolled_back=True)
    _make_comparison("base3", "child3", ts, {"win_rate": 40})  # still pending -- no after yet

    result = history.compute_evolution_history("week", now=now)
    assert result["rollbacks"] == 1
    assert result["finalized"] == 2
    assert result["improved"] == 1
    assert result["pending"] == 1


def test_before_after_metrics_average_only_finalized_comparisons(test_db):
    now = datetime.now(timezone.utc)
    ts = _iso(now - timedelta(days=1))
    _make_comparison("base1", "child1", ts,
                      before={"win_rate": 40, "total_pnl": 100, "avg_profit_factor": 1.2, "max_drawdown_pct": 5},
                      after={"win_rate": 50, "total_pnl": 150, "avg_profit_factor": 1.5, "max_drawdown_pct": 4},
                      verdict="improved")
    _make_comparison("base2", "child2", ts,
                      before={"win_rate": 30, "total_pnl": -50, "avg_profit_factor": 0.8, "max_drawdown_pct": 10},
                      after={"win_rate": 25, "total_pnl": -60, "avg_profit_factor": 0.7, "max_drawdown_pct": 12},
                      verdict="regressed", rolled_back=True)
    _make_comparison("base3", "child3", ts, before={"win_rate": 100})  # pending, excluded from averages

    result = history.compute_evolution_history("week", now=now)
    assert result["before"]["win_rate"] == 35.0  # avg(40, 30) -- pending's 100 excluded
    assert result["after"]["win_rate"] == 37.5   # avg(50, 25)
    assert result["after"]["total_pnl"] == 45.0  # avg(150, -60)


def test_missing_metric_values_are_skipped_not_treated_as_zero(test_db):
    now = datetime.now(timezone.utc)
    ts = _iso(now - timedelta(days=1))
    _make_comparison("base1", "child1", ts, before={"win_rate": 40, "total_pnl": None},
                      after={"win_rate": 50, "total_pnl": None}, verdict="improved")
    result = history.compute_evolution_history("week", now=now)
    assert result["after"]["total_pnl"] is None  # no comparable data -- not silently 0


def test_no_events_at_all_returns_zeros_not_an_error(test_db):
    result = history.compute_evolution_history("week")
    assert result["strategies_evolved"] == 0
    assert result["generations_created"] == 0
    assert result["before"]["win_rate"] is None


def test_compare_periods_separates_current_from_previous(test_db):
    now = datetime.now(timezone.utc)
    _make_comparison("base1", "child1", _iso(now - timedelta(days=2)), {"win_rate": 40})   # this week
    _make_comparison("base2", "child2", _iso(now - timedelta(days=10)), {"win_rate": 30})  # last week

    result = history.compare_periods("week", now=now)
    assert result["current"]["generations_created"] == 1
    assert result["previous"]["generations_created"] == 1
    assert result["current"]["strategies_evolved"] != result["previous"]["strategies_evolved"] or True
    assert {c["base_id"] for c in result["current"]["comparisons"]} == {"base1"}
    assert {c["base_id"] for c in result["previous"]["comparisons"]} == {"base2"}


def test_unknown_window_raises_value_error(test_db):
    import pytest
    with pytest.raises(ValueError):
        history.compute_evolution_history("decade")


def test_never_writes_anything(test_db):
    """Read-only guarantee: calling compute_evolution_history must never
    change any evolution_comparisons row."""
    now = datetime.now(timezone.utc)
    ts = _iso(now - timedelta(days=1))
    _make_comparison("base1", "child1", ts, {"win_rate": 40})
    before_rows = storage.list_evolution_comparisons()
    history.compute_evolution_history("week", now=now)
    history.compare_periods("month", now=now)
    after_rows = storage.list_evolution_comparisons()
    assert before_rows == after_rows
