import pandas as pd
import pytest

from paper_trading import market_data_guard as guard
from paper_trading import health_check


def _stale_frame():
    idx = pd.date_range("2026-01-01", periods=30, freq="1h")
    return pd.DataFrame({"open": 1.0, "high": 1.1, "low": 0.9, "close": 1.0, "volume": 1.0}, index=idx)


def test_stale_frame_is_skipped_logged_and_counted(monkeypatch):
    lines = []
    from data_engine import logging_setup
    monkeypatch.setattr(logging_setup, "log", lambda m: lines.append(m))
    before = guard.rejection_summary()["total_since_start"]
    with pytest.raises(guard.MarketDataRejected):
        guard.closed_recent_frame(_stale_frame(), "1h")  # years old -> stale
    summary = guard.rejection_summary()
    assert summary["total_since_start"] == before + 1
    assert summary["rejected_in_window"] >= 1
    assert any("WARNING" in m and "rejected" in m for m in lines)


def test_health_check_exposes_the_rejection_metric():
    check = health_check._check_market_data_rejections()
    assert check["name"].startswith("Market-data rejections")
    assert "metrics" in check and "total_since_start" in check["metrics"]
