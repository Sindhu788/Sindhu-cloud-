"""Grand Master Batch, Phase 4 Item 4 -- Confidence Trend graph.

paper_positions.confidence already stored a real value per position
since it was first added -- this only surfaces it as an oldest-first
time series, no new column, no backfill.
"""

from datetime import datetime, timezone

from data_engine import storage


def _open(pos_id, strategy_id, confidence, entry_time_ms):
    storage.open_paper_position({
        "id": pos_id, "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": entry_time_ms, "created_at": datetime.now(timezone.utc).isoformat(),
        "strategy_id": strategy_id, "strategy_name": strategy_id, "confidence": confidence,
    })


def test_empty_when_no_positions(test_db):
    assert storage.list_confidence_history("strat1") == []


def test_returns_oldest_first(test_db):
    _open("p1", "strat1", 60.0, 3000)
    _open("p2", "strat1", 80.0, 1000)
    _open("p3", "strat1", 70.0, 2000)
    history = storage.list_confidence_history("strat1")
    assert [h["confidence"] for h in history] == [80.0, 70.0, 60.0]
    assert [h["entry_time"] for h in history] == [1000, 2000, 3000]


def test_only_this_strategys_positions_are_included(test_db):
    _open("p1", "strat1", 60.0, 1000)
    _open("p2", "strat2", 90.0, 2000)
    history = storage.list_confidence_history("strat1")
    assert len(history) == 1
    assert history[0]["confidence"] == 60.0


def test_positions_with_no_confidence_recorded_are_excluded(test_db):
    storage.open_paper_position({
        "id": "p1", "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": 1000, "created_at": datetime.now(timezone.utc).isoformat(),
        "strategy_id": "strat1", "strategy_name": "strat1",
    })
    assert storage.list_confidence_history("strat1") == []


def test_limit_caps_how_many_most_recent_are_returned(test_db):
    for i in range(5):
        _open(f"p{i}", "strat1", float(i), i * 1000)
    history = storage.list_confidence_history("strat1", limit=2)
    assert len(history) == 2
    # Still oldest-first WITHIN the limited (most recent N) window.
    assert [h["confidence"] for h in history] == [3.0, 4.0]
