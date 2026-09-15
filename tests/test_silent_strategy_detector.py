"""Grand Master Batch #2, Phase 4.6: real evidence for the Silent Strategy
Detector -- flags enabled strategies that haven't opened a real position
in a long time, using only real stored data.
"""

from datetime import datetime, timedelta, timezone

import pytest

from data_engine import config as base_config, storage
from paper_trading import silent_strategy_detector


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _iso(days_ago):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _enable(strategy_id, updated_at_days_ago=0):
    storage.save_paper_strategy_config(strategy_id, True, 1, [], [], _iso(updated_at_days_ago))


def _open_position(strategy_id, created_days_ago):
    storage.open_paper_position({
        "id": f"{strategy_id}-{created_days_ago}", "exchange": "binance", "symbol": "BTCUSDT",
        "direction": "long", "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": 1700000000000, "created_at": _iso(created_days_ago),
        "strategy_id": strategy_id, "strategy_name": strategy_id,
    })


def test_active_strategy_is_not_flagged(test_db):
    _enable("stratA", updated_at_days_ago=60)
    _open_position("stratA", created_days_ago=2)
    flagged = silent_strategy_detector.detect_silent_strategies(min_days_silent=14)
    assert not any(f["strategy_id"] == "stratA" for f in flagged)


def test_strategy_silent_past_threshold_is_flagged(test_db):
    _enable("stratB", updated_at_days_ago=60)
    _open_position("stratB", created_days_ago=20)
    flagged = silent_strategy_detector.detect_silent_strategies(min_days_silent=14)
    match = next(f for f in flagged if f["strategy_id"] == "stratB")
    assert match["days_silent"] == 20
    assert "no new position opened" in match["reason"]


def test_disabled_strategy_being_silent_is_not_flagged(test_db):
    storage.save_paper_strategy_config("stratC", False, 1, [], [], _iso(60))
    _open_position("stratC", created_days_ago=100)
    flagged = silent_strategy_detector.detect_silent_strategies(min_days_silent=14)
    assert not any(f["strategy_id"] == "stratC" for f in flagged)


def test_enabled_strategy_that_never_traded_is_always_flagged(test_db):
    _enable("stratD", updated_at_days_ago=1)
    flagged = silent_strategy_detector.detect_silent_strategies(min_days_silent=14)
    match = next(f for f in flagged if f["strategy_id"] == "stratD")
    assert match["last_activity_at"] is None
    assert "never opened" in match["reason"]


def test_sorted_worst_first(test_db):
    _enable("stratE", updated_at_days_ago=60)
    _open_position("stratE", created_days_ago=15)
    _enable("stratF", updated_at_days_ago=60)
    _open_position("stratF", created_days_ago=40)
    flagged = silent_strategy_detector.detect_silent_strategies(min_days_silent=14)
    ids_in_order = [f["strategy_id"] for f in flagged]
    assert ids_in_order.index("stratF") < ids_in_order.index("stratE")


def test_endpoint_is_reachable(test_db):
    from sindhu_web.api.paper_trading import get_silent_strategies
    result = get_silent_strategies()
    assert "flagged" in result
