"""scripts/migrate_to_postgres.py -- copies only the lightweight cloud
runner's curated tables from the real local SQLite database into Postgres.

No real Postgres server is available in this environment (same honest
limitation as tests/test_db_backend.py), so these tests cover exactly
what can be verified without one: the SQL-building logic (column
intersection between the two schemas, the ON CONFLICT clause, which rows
get read and in what shape) against a mocked psycopg2 cursor -- the exact
same "prove the calling convention is correct" scope as test_db_backend.py.
A real round-trip happens on Railway, using this same script, after
deployment.
"""

import importlib.util
import os
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "migrate_to_postgres.py"
_spec = importlib.util.spec_from_file_location("migrate_to_postgres", _SCRIPT_PATH)
migrate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrate)


def _sqlite_with_table(tmp_path, table, columns, rows):
    db_path = tmp_path / "source.db"
    conn = sqlite3.connect(str(db_path))
    col_defs = ", ".join(f"{c} TEXT" for c in columns)
    conn.execute(f"CREATE TABLE {table} ({col_defs})")
    conn.executemany(f"INSERT INTO {table} VALUES ({','.join('?' * len(columns))})", rows)
    conn.commit()
    return conn


def _mock_pg_cursor(pg_columns, pk_columns):
    """A MagicMock cursor whose .execute() answers information_schema /
    pg_index introspection queries the real functions issue, and records
    the final INSERT for inspection."""
    cur = MagicMock()
    cur.rowcount = -1  # psycopg2's real "unknown" sentinel for executemany

    def _execute(sql, params=None):
        if "information_schema.columns" in sql:
            cur.fetchall.return_value = [(c,) for c in pg_columns]
        elif "pg_index" in sql:
            cur.fetchall.return_value = [(c,) for c in pk_columns]
    cur.execute.side_effect = _execute
    return cur


def test_migrates_only_columns_present_on_both_sides(tmp_path):
    """The local SQLite table has an extra legacy column the curated
    Postgres schema does not -- must be silently excluded, never crash."""
    sqlite_conn = _sqlite_with_table(
        tmp_path, "paper_alerts",
        columns=["id", "message", "some_legacy_column"],
        rows=[("1", "hello", "old-data")],
    )
    pg_cur = _mock_pg_cursor(pg_columns=["id", "message"], pk_columns=["id"])
    pg_conn = MagicMock()
    pg_conn.cursor.return_value = pg_cur

    count = migrate.migrate_table(sqlite_conn, pg_conn, "paper_alerts")

    assert count == 1
    insert_sql, insert_rows = pg_cur.executemany.call_args[0]
    assert "some_legacy_column" not in insert_sql
    assert "id" in insert_sql and "message" in insert_sql
    assert insert_rows == [("1", "hello")]


def test_missing_column_on_sqlite_side_does_not_crash(tmp_path, capsys):
    """A column the curated schema expects but the local database doesn't
    have (e.g. an older database) must be reported, not crash the run."""
    sqlite_conn = _sqlite_with_table(
        tmp_path, "paper_alerts", columns=["id"], rows=[("1",)],
    )
    pg_cur = _mock_pg_cursor(pg_columns=["id", "message"], pk_columns=["id"])
    pg_conn = MagicMock()
    pg_conn.cursor.return_value = pg_cur

    count = migrate.migrate_table(sqlite_conn, pg_conn, "paper_alerts")

    assert count == 1
    insert_sql, insert_rows = pg_cur.executemany.call_args[0]
    assert "message" not in insert_sql
    assert insert_rows == [("1",)]
    assert "missing" in capsys.readouterr().out.lower()


def test_conflict_clause_uses_the_real_primary_key_not_a_guess(tmp_path):
    sqlite_conn = _sqlite_with_table(
        tmp_path, "paper_strategy_stat_archives", columns=["strategy_id", "archived_at"],
        rows=[("s1", "2026-01-01")],
    )
    pg_cur = _mock_pg_cursor(
        pg_columns=["strategy_id", "archived_at"], pk_columns=["strategy_id", "archived_at"],
    )
    pg_conn = MagicMock()
    pg_conn.cursor.return_value = pg_cur

    migrate.migrate_table(sqlite_conn, pg_conn, "paper_strategy_stat_archives")

    insert_sql = pg_cur.executemany.call_args[0][0]
    assert "ON CONFLICT (strategy_id, archived_at) DO NOTHING" in insert_sql


def test_table_absent_from_local_database_is_skipped_not_fatal(tmp_path, capsys):
    db_path = tmp_path / "empty.db"
    sqlite_conn = sqlite3.connect(str(db_path))
    pg_conn = MagicMock()

    count = migrate.migrate_table(sqlite_conn, pg_conn, "bot_lessons")

    assert count == 0
    pg_conn.cursor.assert_not_called()
    assert "skipped" in capsys.readouterr().out.lower()


def test_empty_table_migrates_zero_rows_without_calling_executemany(tmp_path):
    sqlite_conn = _sqlite_with_table(tmp_path, "lessons", columns=["id"], rows=[])
    pg_cur = _mock_pg_cursor(pg_columns=["id"], pk_columns=["id"])
    pg_conn = MagicMock()
    pg_conn.cursor.return_value = pg_cur

    count = migrate.migrate_table(sqlite_conn, pg_conn, "lessons")

    assert count == 0
    pg_cur.executemany.assert_not_called()


def test_curated_table_list_matches_db_backend_schema_exactly():
    """This script's CURATED_TABLES must never silently drift from the
    schema data_engine/db_backend.py actually creates in Postgres --
    otherwise a table could go un-migrated with no warning."""
    from data_engine import db_backend
    schema_tables = set(migrate.CURATED_TABLES)
    import re
    declared = set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", db_backend.POSTGRES_SCHEMA))
    assert schema_tables == declared


def test_main_refuses_to_run_without_database_url(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    try:
        migrate.main()
        assert False, "should have exited"
    except SystemExit as e:
        assert e.code != 0
    assert "DATABASE_URL" in capsys.readouterr().out
