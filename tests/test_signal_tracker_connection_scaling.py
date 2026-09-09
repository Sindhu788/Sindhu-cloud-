"""Urgent bug fix, 2026-09-09: GET /api/paper-trading/signal-tracker/
match-table (the Signal Tracker page) called
storage.latest_completed_batch_for_strategy_name() once PER STRATEGY
inside strategy_match_table()'s loop -- each its own fresh Postgres
connection, and on the cloud runner each one also raised UndefinedTable
(backtest_batches is deliberately excluded from POSTGRES_SCHEMA), so at
75 enabled strategies this was 75 connection-open-then-immediately-fail
round trips for one read-only reporting page. Same for
check_and_alert_divergence()'s per-row get_recent_paper_alert() call.
Both replaced with one batched query each.
"""
from datetime import datetime, timezone, timedelta

import pytest

from data_engine import config as base_config, storage
from paper_trading import signal_tracker


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _close(position_id, pnl, strategy_id, strategy_name, days_ago=0):
    pos = {
        "id": position_id, "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": 1700000000000,
        "created_at": (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(),
        "strategy_id": strategy_id, "strategy_name": strategy_name,
    }
    storage.open_paper_position(pos)
    storage.close_paper_position(
        position_id, 100.0 + pnl, 1700000100000, pnl, pnl,
        "take_profit" if pnl >= 0 else "stop_loss", {}, {},
        (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(),
    )


def _counting_get_conn(monkeypatch):
    call_count = {"n": 0}
    real_get_conn = storage.get_conn

    def counting():
        call_count["n"] += 1
        return real_get_conn()

    monkeypatch.setattr(storage, "get_conn", counting)
    return call_count


def _make_completed_batch(batch_id, strategy_name, total_trades, wins):
    storage.create_batch(batch_id, strategy_name, "binance", {"initial_balance": 1000.0}, "2026-01-01T00:00:00+00:00")
    storage.save_result(
        batch_id, "BTCUSDT", "1h", "completed",
        {"total_trades": total_trades, "wins": wins, "final_balance": 1100.0,
         "profit_pct": 10.0, "max_drawdown_pct": 5.0},
        "2026-01-01T00:00:00+00:00",
    )
    storage.update_batch_status(batch_id, "completed", "2026-01-01T00:00:00+00:00")


def test_match_table_stays_low_on_connections_at_scale(test_db, monkeypatch):
    for i in range(40):
        sid = f"strat{i}"
        _close(f"p{i}", 10.0 if i % 2 else -5.0, sid, sid, days_ago=i % 5)

    call_count = _counting_get_conn(monkeypatch)
    table = signal_tracker.strategy_match_table()

    assert len(table["strategies"]) == 40
    # Before this fix: at minimum one connection per strategy from
    # _backtest_win_rate's own lookup, on top of the shared queries this
    # already made. Now: a small constant regardless of strategy count.
    assert call_count["n"] < 6


def test_match_table_still_finds_a_real_completed_batch_by_name(test_db):
    _close("p1", 10.0, "strat1", "My Strategy")
    _make_completed_batch("batch1", "My Strategy", total_trades=10, wins=7)

    table = signal_tracker.strategy_match_table()
    row = next(r for r in table["strategies"] if r["strategy_id"] == "strat1")
    assert row["backtest_batch_id"] == "batch1"
    assert row["backtest_win_rate"] == 70.0


def test_match_table_degrades_gracefully_when_backtest_batches_is_missing(test_db, monkeypatch):
    """Mirrors the real cloud-runner condition (backtest_batches doesn't
    exist in POSTGRES_SCHEMA) -- must not crash the whole page."""
    _close("p1", 10.0, "strat1", "My Strategy")
    monkeypatch.setattr(storage, "latest_completed_batches_for_strategy_names",
                         lambda names: (_ for _ in ()).throw(Exception('relation "backtest_batches" does not exist')))

    table = signal_tracker.strategy_match_table()
    row = next(r for r in table["strategies"] if r["strategy_id"] == "strat1")
    assert row["backtest_win_rate"] is None
    assert row["backtest_batch_id"] is None


def test_check_and_alert_divergence_stays_low_on_connections_at_scale(test_db, monkeypatch):
    for i in range(40):
        sid = f"strat{i}"
        _close(f"p{i}", -5.0, sid, sid, days_ago=i % 5)

    call_count = _counting_get_conn(monkeypatch)
    signal_tracker.check_and_alert_divergence()

    assert call_count["n"] < 6
