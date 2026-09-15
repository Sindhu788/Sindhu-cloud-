"""Grand Master Batch #2, Phase 2.3: real evidence for Signal Quality
Calibration -- do signals stated at "X% confidence" actually win ~X% of
the time, computed only from real closed paper trades, never fabricated.
"""

import pytest

from data_engine import config as base_config, storage
from paper_trading import confidence_calibration


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _trade(pid, confidence, pnl):
    storage.open_paper_position({
        "id": pid, "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": 1700000000000, "created_at": "2026-01-01T00:00:00+00:00",
        "strategy_id": "strat1", "strategy_name": "Test Strategy", "confidence": confidence,
    })
    storage.close_paper_position(
        pid, 100.0 + pnl, 1700000600000, pnl, pnl, "take_profit", {}, {}, "2026-01-02T00:00:00+00:00",
    )


def test_returns_all_ten_buckets_even_when_empty(test_db):
    result = confidence_calibration.compute_calibration_map()
    assert len(result) == 10
    assert result[0]["bucket_range"] == "0-10%"
    assert result[9]["bucket_range"] == "90-100%"
    assert all(b["sample_size"] == 0 and b["trustworthy"] is False for b in result)


def test_bucket_reports_real_win_rate_once_trustworthy(test_db):
    # 25 real trades stated at ~75% confidence: 15 wins, 10 losses = 60% real win rate.
    for i in range(15):
        _trade(f"w{i}", confidence=75.0, pnl=10.0)
    for i in range(10):
        _trade(f"l{i}", confidence=75.0, pnl=-5.0)

    result = confidence_calibration.compute_calibration_map()
    bucket = next(b for b in result if b["bucket_range"] == "70-80%")
    assert bucket["sample_size"] == 25
    assert bucket["trustworthy"] is True
    assert bucket["real_win_rate_pct"] == 60.0
    assert bucket["stated_avg_confidence"] == 75.0


def test_bucket_below_minimum_sample_is_not_trustworthy(test_db):
    for i in range(5):
        _trade(f"w{i}", confidence=75.0, pnl=10.0)
    result = confidence_calibration.compute_calibration_map()
    bucket = next(b for b in result if b["bucket_range"] == "70-80%")
    assert bucket["sample_size"] == 5
    assert bucket["trustworthy"] is False


def test_100_percent_confidence_clamps_into_top_bucket(test_db):
    for i in range(25):
        _trade(f"t{i}", confidence=100.0, pnl=5.0)
    result = confidence_calibration.compute_calibration_map()
    bucket = next(b for b in result if b["bucket_range"] == "90-100%")
    assert bucket["sample_size"] == 25


def test_calibrated_win_rate_for_returns_none_when_untrustworthy(test_db):
    for i in range(5):
        _trade(f"w{i}", confidence=75.0, pnl=10.0)
    rate, trustworthy, n = confidence_calibration.calibrated_win_rate_for(74.0)
    assert rate is None and trustworthy is False and n == 5


def test_calibrated_win_rate_for_returns_real_value_when_trustworthy(test_db):
    for i in range(20):
        _trade(f"w{i}", confidence=42.0, pnl=10.0)
    for i in range(5):
        _trade(f"l{i}", confidence=42.0, pnl=-3.0)
    rate, trustworthy, n = confidence_calibration.calibrated_win_rate_for(45.0)
    assert trustworthy is True
    assert rate == 80.0
    assert n == 25


def test_endpoint_is_reachable(test_db):
    from sindhu_web.api.paper_trading import get_confidence_calibration
    result = get_confidence_calibration()
    assert len(result["buckets"]) == 10
