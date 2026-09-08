"""Urgent bug fix, 2026-09-09: GET /api/paper-trading/status timed out
(15000ms) on Render -- confirmed the dashboard's most heavily-polled
endpoint was opening 3 separate fresh Postgres connections per request
(no connection pooling on the cloud runner -- see data_engine.db_backend.
get_postgres_conn's own docstring), compounding under the concurrent
request load a full Paper Trading page load fires. storage.
get_paper_status_snapshot() now answers all 3 needs (open positions,
per-strategy account states, today's trade count) from ONE connection.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from data_engine import config as base_config, storage
from paper_trading.engine import engine as real_engine


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _open_position(**overrides):
    pos = {
        "id": overrides.pop("id", "pos1"), "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": 1700000000000, "created_at": "2026-01-01T00:00:00+00:00",
        "strategy_id": "strat1", "strategy_name": "Test Strategy",
    }
    pos.update(overrides)
    storage.open_paper_position(pos)
    return pos


def test_snapshot_returns_open_positions_states_and_trades_today(test_db):
    now_iso = datetime.now(timezone.utc).isoformat()
    yesterday_iso = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    _open_position(id="today", created_at=now_iso)
    _open_position(id="yesterday", created_at=yesterday_iso, strategy_id="strat2")

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    open_positions, states, trades_today = storage.get_paper_status_snapshot(today_start)

    assert len(open_positions) == 2
    assert {p["id"] for p in open_positions} == {"today", "yesterday"}
    assert trades_today == 1


def test_snapshot_uses_exactly_one_connection(test_db, monkeypatch):
    """The whole point of the fix: one get_conn() call, not three."""
    _open_position()
    call_count = {"n": 0}
    real_get_conn = storage.get_conn

    def counting_get_conn():
        call_count["n"] += 1
        return real_get_conn()

    monkeypatch.setattr(storage, "get_conn", counting_get_conn)
    storage.get_paper_status_snapshot(datetime.now(timezone.utc).isoformat())
    assert call_count["n"] == 1


def test_engine_status_uses_the_consolidated_snapshot(test_db, monkeypatch):
    """engine.status() must call the new single-connection snapshot, not
    the three separate storage functions it used to call independently."""
    _open_position(created_at=datetime.now(timezone.utc).isoformat())
    monkeypatch.setattr(storage, "get_open_paper_positions",
                         lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not be called directly")))
    monkeypatch.setattr(storage, "list_paper_account_states",
                         lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not be called directly")))
    monkeypatch.setattr(storage, "count_paper_trades_opened_since",
                         lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not be called directly")))

    status = real_engine.status()

    assert status["open_trades"] == 1
    assert status["trades_today"] == 1
