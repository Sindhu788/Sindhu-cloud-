"""Grand Master Batch, Phase 4 Item 9 -- Best time to check dashboard."""

from datetime import datetime, timezone

from data_engine import storage
from paper_trading import best_check_time


def _log_send(hour, success=True):
    storage.log_telegram_message(
        "pos1", "strat1", "Test Strategy", "manual", "text", success, None,
        f"2026-01-01T{hour:02d}:15:00+00:00",
    )


def test_not_enough_data_gives_no_suggestion(test_db):
    for _ in range(5):
        _log_send(9)
    result = best_check_time.best_check_times()
    assert result["has_enough_data"] is False
    assert result["best_hours_utc"] == []


def test_identifies_the_busiest_hour(test_db):
    for _ in range(15):
        _log_send(14)
    for _ in range(3):
        _log_send(2)
    result = best_check_time.best_check_times(top_n=1)
    assert result["has_enough_data"] is True
    assert result["best_hours_utc"] == [14]
    assert result["total_signals"] == 18


def test_hourly_counts_cover_all_24_hours_zero_filled(test_db):
    for _ in range(10):
        _log_send(5)
    result = best_check_time.best_check_times()
    assert len(result["hourly_counts"]) == 24
    hour_5 = next(h for h in result["hourly_counts"] if h["hour_utc"] == 5)
    assert hour_5["count"] == 10
    hour_0 = next(h for h in result["hourly_counts"] if h["hour_utc"] == 0)
    assert hour_0["count"] == 0


def test_failed_sends_are_never_counted(test_db):
    for _ in range(15):
        _log_send(9, success=False)
    result = best_check_time.best_check_times()
    assert result["has_enough_data"] is False
    assert result["total_signals"] == 0


def test_top_n_returns_multiple_busiest_hours_in_order(test_db):
    for _ in range(20):
        _log_send(10)
    for _ in range(15):
        _log_send(20)
    for _ in range(11):
        _log_send(3)
    result = best_check_time.best_check_times(top_n=2)
    assert result["best_hours_utc"] == [10, 20]
