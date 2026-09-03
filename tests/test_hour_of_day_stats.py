"""Grand Feature Expansion, Phase 3 Feature 10: Time-of-Day Performance
Breakdown by UTC HOUR (data_engine/storage.py's list_paper_hour_of_day_stats),
more granular than the pre-existing list_paper_session_stats (named
sessions: asian/london/ny).
"""

from data_engine import storage


def _close(position_id, pnl, created_at, strategy_id="strat1"):
    pos = {
        "id": position_id, "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": 1700000000000, "created_at": created_at,
        "strategy_id": strategy_id, "strategy_name": "Test Strategy",
    }
    storage.open_paper_position(pos)
    storage.close_paper_position(
        position_id, 100.0 + pnl, 1700000100000, pnl, pnl,
        "take_profit" if pnl >= 0 else "stop_loss", {}, {}, created_at,
    )


def test_groups_trades_by_utc_entry_hour(test_db):
    _close("p1", pnl=10.0, created_at="2026-01-01T09:15:00+00:00")
    _close("p2", pnl=-5.0, created_at="2026-01-01T09:45:00+00:00")
    _close("p3", pnl=20.0, created_at="2026-01-01T14:00:00+00:00")

    hours = storage.list_paper_hour_of_day_stats()
    by_hour = {h["hour_utc"]: h for h in hours}
    assert by_hour[9]["closed_trades"] == 2
    assert by_hour[9]["total_pnl"] == 5.0
    assert by_hour[9]["win_rate"] == 50.0
    assert by_hour[14]["closed_trades"] == 1
    assert by_hour[14]["win_rate"] == 100.0


def test_filters_by_strategy_id(test_db):
    _close("p1", pnl=10.0, created_at="2026-01-01T09:00:00+00:00", strategy_id="strat1")
    _close("p2", pnl=10.0, created_at="2026-01-01T09:00:00+00:00", strategy_id="strat2")

    hours = storage.list_paper_hour_of_day_stats(strategy_id="strat1")
    assert len(hours) == 1
    assert hours[0]["closed_trades"] == 1


def test_filters_by_since_and_until(test_db):
    _close("p1", pnl=10.0, created_at="2026-01-01T09:00:00+00:00")
    _close("p2", pnl=10.0, created_at="2026-02-01T09:00:00+00:00")

    hours = storage.list_paper_hour_of_day_stats(since_iso="2026-01-15T00:00:00+00:00")
    assert sum(h["closed_trades"] for h in hours) == 1


def test_empty_when_nothing_closed_yet(test_db):
    assert storage.list_paper_hour_of_day_stats() == []


def test_hours_are_sorted_ascending(test_db):
    _close("p1", pnl=1.0, created_at="2026-01-01T22:00:00+00:00")
    _close("p2", pnl=1.0, created_at="2026-01-01T03:00:00+00:00")
    _close("p3", pnl=1.0, created_at="2026-01-01T11:00:00+00:00")

    hours = [h["hour_utc"] for h in storage.list_paper_hour_of_day_stats()]
    assert hours == sorted(hours)
