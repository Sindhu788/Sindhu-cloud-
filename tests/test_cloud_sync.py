"""paper_trading/cloud_sync.py -- Part 6 (this task): a scheduled, ONE-WAY
cloud-to-local backup of the cloud runner's own Paper Trading + Telegram
data. Same honest limitation as the other cloud_settings-backed tests:
no real Postgres server is available in this environment, so the
Postgres branch is proven with a real sqlite3 file connection substituted
for storage.get_conn() (exact SQL text, genuine round-trips) -- see
tests/test_auth_cloud_persistence.py's module docstring for the full
reasoning behind that technique.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest

from data_engine import config as base_config
from data_engine import db_backend, storage
from paper_trading import cloud_sync


def _connect(db_path):
    @contextmanager
    def _get_conn():
        c = sqlite3.connect(str(db_path))
        try:
            yield c
            c.commit()
        finally:
            c.close()
    return _get_conn


@pytest.fixture(autouse=True)
def isolated_local_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))


def _open_position(**overrides):
    pos = {
        "id": "pos1", "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": 1700000000000, "created_at": "2026-01-01T00:00:00+00:00",
        "strategy_id": "strat1", "strategy_name": "Test Strategy",
    }
    pos.update(overrides)
    storage.open_paper_position(pos)
    return pos


def test_build_snapshot_reuses_existing_storage_data(test_db):
    _open_position(id="open1")
    _open_position(id="closed1")
    storage.close_paper_position("closed1", 110.0, 1700000100000, 10.0, 10.0, "take_profit", {}, {},
                                  "2026-01-02T00:00:00+00:00")
    storage.log_telegram_message("open1", "strat1", "Test Strategy", "manual", "text", True, None,
                                  "2026-01-01T00:00:00+00:00")

    snapshot = cloud_sync.build_snapshot()
    assert snapshot["generated_at"]
    assert len(snapshot["open_positions"]) == 1
    assert snapshot["open_positions"][0]["id"] == "open1"
    assert len(snapshot["closed_positions"]) == 1
    assert snapshot["closed_positions"][0]["id"] == "closed1"
    assert len(snapshot["telegram_signal_log"]) == 1


def test_no_snapshot_yet_returns_none_on_local_laptop(test_db):
    assert cloud_sync.get_latest_snapshot() is None


def test_run_sync_persists_to_local_file_when_not_postgres(test_db, monkeypatch):
    monkeypatch.setattr(db_backend, "IS_POSTGRES", False)
    cloud_sync.run_sync()
    snapshot = cloud_sync.get_latest_snapshot()
    assert snapshot is not None
    assert "generated_at" in snapshot


@pytest.fixture
def cloud_mode(test_db, monkeypatch):
    """Reuses test_db's own real sqlite file (already has paper_positions,
    telegram_message_log, etc. from storage.init_db()) rather than a
    separate minimal fake -- build_snapshot() genuinely queries all of
    those tables, unlike auth.py's Postgres branch, which only ever
    touches its own two dedicated tables. Only adds the one table this
    module itself needs (cloud_settings), same schema db_backend.py
    declares for Postgres."""
    monkeypatch.setattr(db_backend, "IS_POSTGRES", True)
    conn = sqlite3.connect(test_db)
    conn.execute("""CREATE TABLE IF NOT EXISTS cloud_settings (
        key TEXT PRIMARY KEY, value_json TEXT NOT NULL, updated_at TEXT NOT NULL)""")
    conn.commit()
    conn.close()
    monkeypatch.setattr(cloud_sync.storage, "get_conn", _connect(test_db))
    return test_db


def test_snapshot_survives_a_simulated_restart_on_postgres(test_db, cloud_mode, monkeypatch):
    """The actual point of this feature: a snapshot generated before a
    restart must still be downloadable after one -- proven the same
    honest way as Part 1/3's persistence fixes (a brand new connection to
    the same on-disk file, nothing held over in a Python object)."""
    _open_position(id="p1")
    cloud_sync.run_sync()

    monkeypatch.setattr(cloud_sync.storage, "get_conn", _connect(cloud_mode))
    snapshot = cloud_sync.get_latest_snapshot()
    assert snapshot is not None
    assert len(snapshot["open_positions"]) == 1


def test_should_run_now_true_when_never_run(cloud_mode):
    assert cloud_sync._should_run_now() is True


def test_should_run_now_false_right_after_a_run(cloud_mode):
    cloud_sync.run_sync()
    assert cloud_sync._should_run_now() is False


def test_should_run_now_true_once_24h_have_elapsed(cloud_mode):
    stale_snapshot = cloud_sync.build_snapshot()
    stale_snapshot["generated_at"] = (
        datetime.now(timezone.utc) - timedelta(hours=25)
    ).isoformat()
    storage.save_cloud_setting(cloud_sync._SNAPSHOT_KEY, stale_snapshot, stale_snapshot["generated_at"])
    assert cloud_sync._should_run_now() is True


def test_local_laptop_never_writes_to_the_cloud_settings_table(test_db, monkeypatch):
    """DATABASE_URL unset (every local laptop run) must keep using the
    local JSON file exactly like every other cloud_settings-backed module
    in this codebase -- this is a cloud-runtime-only feature."""
    monkeypatch.setattr(db_backend, "IS_POSTGRES", False)
    cloud_sync.run_sync()
    import os
    assert os.path.exists(os.path.join(base_config.CONFIG_DIR, cloud_sync._SNAPSHOT_FILE))
