"""Grand Feature Expansion, Phase 3 Feature 14: Session Time-Tracker
(backtest_engine.duration_tracker.compute_duration_stats) -- durable
backtest-duration history read straight from backtest_batches.created_at
/.updated_at (the moment a batch starts and the exact moment it completes),
rather than the in-memory job_manager registry, which is capped at 200
entries and wiped on every restart -- useless for a real history.
"""

from data_engine import storage
from backtest_engine import duration_tracker


def _make_batch(batch_id, strategy_name, created_at, completed_at, status="completed"):
    storage.create_batch(batch_id, strategy_name, "binance", {"initial_balance": 1000.0}, created_at)
    storage.update_batch_status(batch_id, status, completed_at)


def test_no_batches_reports_zero_not_an_error(test_db):
    result = duration_tracker.compute_duration_stats()
    assert result["count"] == 0
    assert result["avg_duration_seconds"] is None


def test_computes_duration_from_created_to_updated(test_db):
    _make_batch("b1", "Test Strategy", "2026-01-01T00:00:00+00:00", "2026-01-01T00:05:00+00:00")
    result = duration_tracker.compute_duration_stats()
    assert result["count"] == 1
    assert result["batches"][0]["duration_seconds"] == 300.0


def test_only_completed_batches_are_counted(test_db):
    _make_batch("b1", "Done", "2026-01-01T00:00:00+00:00", "2026-01-01T00:05:00+00:00", status="completed")
    _make_batch("b2", "Still Running", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00", status="running")
    result = duration_tracker.compute_duration_stats()
    assert result["count"] == 1
    assert result["batches"][0]["batch_id"] == "b1"


def test_average_and_total_are_correct(test_db):
    _make_batch("b1", "A", "2026-01-01T00:00:00+00:00", "2026-01-01T00:01:00+00:00")  # 60s
    _make_batch("b2", "B", "2026-01-01T00:00:00+00:00", "2026-01-01T00:03:00+00:00")  # 180s
    result = duration_tracker.compute_duration_stats()
    assert result["avg_duration_seconds"] == 120.0
    assert result["total_time_spent_seconds"] == 240.0


def test_slowest_batches_are_ranked_first(test_db):
    _make_batch("fast", "Fast", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:10+00:00")
    _make_batch("slow", "Slow", "2026-01-01T00:00:00+00:00", "2026-01-01T01:00:00+00:00")
    result = duration_tracker.compute_duration_stats()
    assert result["slowest"][0]["batch_id"] == "slow"


def test_negative_duration_from_clock_skew_is_skipped_not_reported(test_db):
    _make_batch("bad", "Bad Timestamps", "2026-01-01T01:00:00+00:00", "2026-01-01T00:00:00+00:00")
    result = duration_tracker.compute_duration_stats()
    assert result["count"] == 0
