"""Grand Master Batch #2, Phase 1.5: real evidence that backups are only
ever reported successful when an actual restore test (against a throwaway
scratch destination, never the live database) confirms the file is usable
-- not just "the file exists and has a plausible size". Also covers the
real bug found while building this: sindhu_web/api/backup.py always used
sqlite3.connect(DB_PATH) regardless of backend, which is not the real
database when Postgres (DATABASE_URL) is the live backend.
"""

import contextlib
import gzip
import json
import os
import sqlite3

import pytest

from data_engine import config as base_config, db_backend, storage
from sindhu_web.api import backup


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch, test_db):
    monkeypatch.setattr(backup, "DB_PATH", test_db)
    monkeypatch.setattr(backup, "_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(backup, "_DRILL_STATUS_PATH", str(tmp_path / "drill_status.json"))
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _seed_real_data():
    storage.open_paper_position({
        "id": "pos1", "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": 1700000000000, "created_at": "2026-01-01T00:00:00+00:00",
        "strategy_id": "strat1", "strategy_name": "Test Strategy",
    })


# --------------------------------------------------------------- SQLite path

def test_sqlite_backup_then_verify_reports_ok_with_real_row_counts(test_db):
    _seed_real_data()
    name = backup.create_backup()
    assert name.endswith(".db")

    result = backup.verify_backup(name)
    assert result["ok"] is True
    assert result["backend"] == "sqlite"
    assert result["checked_tables"]["paper_positions"] == 1


def test_sqlite_verify_detects_a_genuinely_corrupted_backup_file(test_db):
    _seed_real_data()
    name = backup.create_backup()
    backup_path = os.path.join(backup._BACKUP_DIR, name)

    # Truncate the real backup file to simulate a corrupted/incomplete write
    # -- this must NOT be reported as a successful, restorable backup.
    with open(backup_path, "r+b") as f:
        f.truncate(200)

    result = backup.verify_backup(name)
    assert result["ok"] is False
    assert result["error"] is not None


def test_verify_latest_backup_endpoint_persists_drill_status(test_db):
    _seed_real_data()
    backup.create_backup()
    result = backup.verify_latest_backup()
    assert result["ok"] is True

    status = backup.get_drill_status()
    assert status["ok"] is True
    assert status["backup_name"] == result["backup_name"]


def test_auto_backup_thread_runs_a_real_drill_immediately(test_db, monkeypatch):
    """The scheduled 6-hourly loop calls verify_backup() right after every
    create_backup() -- simulate one iteration of that body directly rather
    than waiting on the real thread's sleep."""
    _seed_real_data()
    name = backup.create_backup()
    result = backup.verify_backup(name)
    backup._save_drill_status(result)
    assert backup.latest_drill_status()["ok"] is True


def test_no_drill_yet_reports_honestly(test_db):
    status = backup.latest_drill_status()
    assert status["ok"] is None


# --------------------------------------------------------------- Postgres path
# No real Postgres server in this test environment (tests always run with
# DATABASE_URL unset) -- dump_postgres_tables() takes a connection as a
# plain argument specifically so its real logic (column/row extraction,
# JSON+gzip round-trip, restore-drill reconstruction) can be exercised
# against a lightweight fake connection that mimics db_backend's real
# _PGConnection/_PGCursorResult interface, instead of skipping this
# entirely.

class _FakeCursor:
    def __init__(self, description, rows):
        self.description = description
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, tables):
        # tables: {table_name: (columns, rows)}
        self._tables = tables

    def execute(self, sql, params=()):
        if sql.startswith("SELECT table_name FROM information_schema"):
            return _FakeCursor(None, [(t,) for t in self._tables])
        for table, (columns, rows) in self._tables.items():
            if f"FROM {table}" in sql:
                return _FakeCursor([(c,) for c in columns], rows)
        if sql.strip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
            # sync.notify()'s own activity-log write also goes through
            # storage.get_conn() when IS_POSTGRES is patched True for this
            # test -- not what's under test here, so accept it as a no-op
            # rather than widening this fake's real assertion surface.
            return _FakeCursor(None, [])
        raise AssertionError(f"unexpected query: {sql}")


def test_dump_postgres_tables_reads_columns_and_rows_from_a_real_query_shape():
    fake_conn = _FakeConn({
        "paper_positions": (["id", "symbol", "pnl"], [["p1", "BTCUSDT", 12.5], ["p2", "ETHUSDT", -3.0]]),
        "kill_switch_state": (["id", "active"], [[1, 0]]),
    })
    dump = backup.dump_postgres_tables(fake_conn)
    assert dump["paper_positions"]["columns"] == ["id", "symbol", "pnl"]
    assert dump["paper_positions"]["rows"] == [["p1", "BTCUSDT", 12.5], ["p2", "ETHUSDT", -3.0]]
    assert dump["kill_switch_state"]["rows"] == [[1, 0]]


def test_postgres_backup_file_verifies_and_fully_reconstructs_real_rows(tmp_path):
    fake_conn = _FakeConn({
        "paper_positions": (["id", "symbol", "pnl"], [["p1", "BTCUSDT", 12.5], ["p2", "ETHUSDT", -3.0]]),
        "kill_switch_state": (["id", "active"], [[1, 0]]),
    })
    dest = str(tmp_path / "sindhu_pg_test.json.gz")
    with gzip.open(dest, "wt", encoding="utf-8") as f:
        json.dump(backup.dump_postgres_tables(fake_conn), f, default=str)

    result = backup._postgres_restore_drill(dest)
    assert result["ok"] is True
    assert result["checked_tables"]["paper_positions"] == 2
    assert result["checked_tables"]["kill_switch_state"] == 1


def test_postgres_verify_detects_a_truncated_dump_file(tmp_path, monkeypatch):
    monkeypatch.setattr(backup, "_BACKUP_DIR", str(tmp_path))
    fake_conn = _FakeConn({"paper_positions": (["id", "symbol"], [["p1", "BTCUSDT"]] * 50)})
    name = "sindhu_pg_test.json.gz"
    dest = str(tmp_path / name)
    with gzip.open(dest, "wt", encoding="utf-8") as f:
        json.dump(backup.dump_postgres_tables(fake_conn), f, default=str)

    # Corrupt the gzip stream itself.
    with open(dest, "r+b") as f:
        data = bytearray(f.read())
        data[10:20] = b"\x00" * 10
        f.seek(0)
        f.write(data)

    # Goes through the real, full verify_backup() path (including its own
    # exception handling), not just the inner drill function -- proving a
    # corrupted file is reported as a failed drill, never a crash or a
    # silent "ok".
    result = backup.verify_backup(name)
    assert result["ok"] is False
    assert result["error"] is not None


def test_create_backup_branches_to_postgres_path_when_is_postgres(tmp_path, monkeypatch):
    monkeypatch.setattr(backup, "_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(db_backend, "IS_POSTGRES", True)

    fake_conn = _FakeConn({"paper_positions": (["id", "symbol"], [["p1", "BTCUSDT"]])})

    @contextlib.contextmanager
    def fake_get_conn():
        yield fake_conn

    monkeypatch.setattr(storage, "get_conn", fake_get_conn)

    name = backup.create_backup()
    assert name.endswith(".json.gz")
    assert os.path.isfile(os.path.join(backup._BACKUP_DIR, name))

    result = backup.verify_backup(name)
    assert result["ok"] is True
    assert result["backend"] == "postgres"


def test_restore_endpoint_refuses_to_automate_postgres_restore(tmp_path, monkeypatch):
    """The one thing this deliberately does NOT automate: replaying a
    Postgres dump back into live production data. Must fail loudly and
    explain why, never silently no-op or silently succeed."""
    monkeypatch.setattr(backup, "_BACKUP_DIR", str(tmp_path / "backups"))
    os.makedirs(backup._BACKUP_DIR, exist_ok=True)
    fake_dump_path = os.path.join(backup._BACKUP_DIR, "sindhu_pg_fake.json.gz")
    with gzip.open(fake_dump_path, "wt", encoding="utf-8") as f:
        json.dump({}, f)

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        backup.restore_backup(backup.RestoreRequest(backup_name="sindhu_pg_fake.json.gz", confirm=True))
    assert exc_info.value.status_code == 501
