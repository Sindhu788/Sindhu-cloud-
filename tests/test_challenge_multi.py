"""Master Task 3, Phase 2.9/2.4/2.15/2.18/2.20: paper_trading/
challenge_multi.py -- multiple independently-tracked challenges, built on
top of the existing single-challenge challenge_mode.compute_progress()
(now settings-injectable) rather than re-deriving its math.
"""

from datetime import datetime, timedelta, timezone

import pytest

from data_engine import config as base_config, storage
from paper_trading import challenge_multi


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _iso(days_ago):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _trade(pid, strategy_id, symbol, pnl, risk_amount, closed_days_ago, entry_time_ms=1700000000000):
    storage.open_paper_position({
        "id": pid, "exchange": "binance", "symbol": symbol, "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": risk_amount,
        "entry_time": entry_time_ms, "created_at": _iso(closed_days_ago),
        "strategy_id": strategy_id, "strategy_name": strategy_id,
    })
    storage.close_paper_position(
        pid, 100.0, entry_time_ms + 30 * 60000, pnl, pnl, "take_profit", {}, {}, _iso(closed_days_ago),
    )


def test_create_challenge_with_named_timeframe_derives_days(test_db):
    c = challenge_multi.create_challenge("Weekly Push", 1000.0, 1200.0, "weekly")
    assert c["days"] == 7
    c2 = challenge_multi.create_challenge("Monthly Push", 1000.0, 1500.0, "monthly")
    assert c2["days"] == 30


def test_create_challenge_custom_requires_explicit_days(test_db):
    with pytest.raises(ValueError):
        challenge_multi.create_challenge("No Days Given", 1000.0, 1200.0, "custom")
    c = challenge_multi.create_challenge("Custom", 1000.0, 1200.0, "custom", days=45)
    assert c["days"] == 45


def test_refuses_a_fourth_simultaneous_challenge(test_db):
    challenge_multi.create_challenge("A", 1000.0, 1200.0, "daily")
    challenge_multi.create_challenge("B", 1000.0, 1200.0, "weekly")
    challenge_multi.create_challenge("C", 1000.0, 1200.0, "monthly")
    with pytest.raises(ValueError):
        challenge_multi.create_challenge("D", 1000.0, 1200.0, "daily")


def test_archiving_one_challenge_frees_a_slot(test_db):
    a = challenge_multi.create_challenge("A", 1000.0, 1200.0, "daily")
    challenge_multi.create_challenge("B", 1000.0, 1200.0, "weekly")
    challenge_multi.create_challenge("C", 1000.0, 1200.0, "monthly")
    challenge_multi.archive_challenge(a["id"])
    d = challenge_multi.create_challenge("D", 1000.0, 1200.0, "daily")
    assert d is not None


def test_compute_progress_for_reuses_challenge_mode_shape(test_db):
    c = challenge_multi.create_challenge("A", 1000.0, 2000.0, "custom", days=30)
    progress = challenge_multi.compute_progress_for(c["id"])
    assert progress["start_amount"] == 1000.0
    assert progress["target_amount"] == 2000.0
    assert progress["challenge_id"] == c["id"]
    assert progress["label"] == "A"
    assert "honest_note" in progress  # reused verbatim from challenge_mode


def test_compute_progress_for_archived_challenge_is_none(test_db):
    c = challenge_multi.create_challenge("A", 1000.0, 2000.0, "custom", days=30)
    challenge_multi.archive_challenge(c["id"])
    assert challenge_multi.compute_progress_for(c["id"]) is None


def test_compute_all_progress_returns_every_active_challenge(test_db):
    challenge_multi.create_challenge("A", 1000.0, 1200.0, "daily")
    challenge_multi.create_challenge("B", 1000.0, 1200.0, "weekly")
    results = challenge_multi.compute_all_progress()
    assert len(results) == 2
    assert {r["label"] for r in results} == {"A", "B"}


def test_extend_deadline_preserves_started_at(test_db):
    c = challenge_multi.create_challenge("A", 1000.0, 1200.0, "daily")
    original_started_at = c["started_at"]
    updated = challenge_multi.extend_deadline(c["id"], 14)
    assert updated["days"] == 14
    assert updated["started_at"] == original_started_at
    assert updated["timeframe_type"] == "custom"


def test_extend_deadline_rejects_zero_or_negative(test_db):
    c = challenge_multi.create_challenge("A", 1000.0, 1200.0, "daily")
    with pytest.raises(ValueError):
        challenge_multi.extend_deadline(c["id"], 0)


def test_compounding_amount_grows_faster_than_fixed_risk_on_a_winning_streak(test_db):
    c = challenge_multi.create_challenge("A", 1000.0, 5000.0, "custom", days=30)
    for i in range(5):
        # Negative days_ago = closed slightly AFTER the challenge's
        # started_at ("now" at creation time), which the compounding
        # calc requires (only trades since the challenge began count).
        _trade(f"t{i}", "__lessons__", "BTCUSDT", 50.0, 20.0, closed_days_ago=-1)
    # Real trades aren't tied to a strategy_id/symbol scope on this
    # unscoped challenge -- challenge_analysis._closed_rows() with no args
    # returns every strategy's real closed trades, matching the unscoped
    # system-wide behavior challenge_mode.compute_progress() itself uses.
    result = challenge_multi.compute_compounding_current_amount(c["id"])
    assert result["trades_counted"] == 5
    assert result["compounding_amount"] > result["fixed_risk_amount"]


def test_compounding_amount_none_for_unknown_challenge(test_db):
    assert challenge_multi.compute_compounding_current_amount("nope") is None


def test_achievability_snapshot_recorded_and_trended(test_db):
    c = challenge_multi.create_challenge("A", 1000.0, 1050.0, "custom", days=30)
    score = challenge_multi.record_achievability_snapshot(c["id"])
    assert score is not None
    trend = challenge_multi.achievability_trend(c["id"], days=7)
    assert len(trend) == 1
    assert trend[0]["achievability_score"] == score


def test_achievability_snapshot_none_for_archived_challenge(test_db):
    c = challenge_multi.create_challenge("A", 1000.0, 1050.0, "custom", days=30)
    challenge_multi.archive_challenge(c["id"])
    assert challenge_multi.record_achievability_snapshot(c["id"]) is None
