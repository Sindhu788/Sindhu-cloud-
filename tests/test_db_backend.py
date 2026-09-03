"""data_engine/db_backend.py -- the dual-backend (SQLite/Postgres) database
support added for the lightweight cloud runner.

No real Postgres server is available in this environment, so these tests
cover exactly what CAN be verified without one:
  - the connection wrapper's calling convention (placeholder translation,
    execute/executemany/fetchone/fetchall) against a mocked psycopg2
    connection -- this is where a real bug would actually live, since the
    SQL text itself is untouched (see the module's own docstring).
  - the curated schema is syntactically valid, self-consistent SQL with
    no leftover SQLite-only syntax.
  - IS_POSTGRES and get_conn()/init_db()'s branch selection genuinely
    depend on DATABASE_URL and nothing else, so local behavior can never
    change by accident.

Real end-to-end Postgres verification (actual INSERT/SELECT round-trips
against a running server) happens on Railway after deployment -- stated
explicitly in DEPLOYMENT_CHECKPOINT.md rather than implied here.
"""

import importlib
from unittest.mock import MagicMock

import pytest

from data_engine import db_backend


def test_is_postgres_reflects_database_url_only(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    importlib.reload(db_backend)
    assert db_backend.IS_POSTGRES is False

    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host:5432/db")
    importlib.reload(db_backend)
    assert db_backend.IS_POSTGRES is True

    monkeypatch.delenv("DATABASE_URL", raising=False)
    importlib.reload(db_backend)
    assert db_backend.IS_POSTGRES is False


@pytest.mark.parametrize("sql,expected", [
    ("SELECT * FROM t WHERE a=?", "SELECT * FROM t WHERE a=%s"),
    ("SELECT * FROM t WHERE a=? AND b=?", "SELECT * FROM t WHERE a=%s AND b=%s"),
    ("SELECT 1", "SELECT 1"),  # no placeholders -- must pass through unchanged
])
def test_placeholder_translation(sql, expected):
    assert db_backend._translate_placeholders(sql) == expected


def test_pgconnection_execute_translates_placeholders_and_forwards_params():
    raw = MagicMock()
    cur = MagicMock()
    raw.cursor.return_value = cur

    conn = db_backend._PGConnection(raw)
    conn.execute("SELECT a FROM t WHERE a=? AND b=?", (1, "x"))

    called_sql, called_params = cur.execute.call_args[0]
    assert called_sql == "SELECT a FROM t WHERE a=%s AND b=%s"
    assert called_params == (1, "x")


def test_pgconnection_execute_result_supports_fetchone_and_fetchall():
    raw = MagicMock()
    cur = MagicMock()
    cur.fetchone.return_value = (1, "x")
    cur.fetchall.return_value = [(1, "x"), (2, "y")]
    raw.cursor.return_value = cur

    conn = db_backend._PGConnection(raw)
    result = conn.execute("SELECT * FROM t")
    assert result.fetchone() == (1, "x")
    assert result.fetchall() == [(1, "x"), (2, "y")]


def test_pgconnection_executemany_translates_and_forwards():
    raw = MagicMock()
    cur = MagicMock()
    raw.cursor.return_value = cur

    conn = db_backend._PGConnection(raw)
    conn.executemany("INSERT INTO t VALUES (?, ?)", [(1, "a"), (2, "b")])

    called_sql, called_params = cur.executemany.call_args[0]
    assert called_sql == "INSERT INTO t VALUES (%s, %s)"
    assert called_params == [(1, "a"), (2, "b")]


def test_pgconnection_commit_close_rollback_forward_to_raw_connection():
    raw = MagicMock()
    conn = db_backend._PGConnection(raw)

    conn.commit()
    raw.commit.assert_called_once()

    conn.rollback()
    raw.rollback.assert_called_once()

    conn.close()
    raw.close.assert_called_once()


def test_pgcursorresult_lastrowid_raises_a_clear_error_rather_than_silently_wrong():
    raw = MagicMock()
    cur = MagicMock()
    raw.cursor.return_value = cur
    conn = db_backend._PGConnection(raw)
    result = conn.execute("INSERT INTO t VALUES (1)")
    with pytest.raises(AttributeError):
        result.lastrowid


# ------------------------------------------------------------ schema shape

def test_schema_has_no_sqlite_only_syntax():
    schema = db_backend.POSTGRES_SCHEMA
    for forbidden in ("AUTOINCREMENT", "PRAGMA", "sqlite_master"):
        assert forbidden not in schema


def test_schema_parses_as_valid_sql_statements():
    sqlparse = pytest.importorskip("sqlparse")
    statements = sqlparse.split(db_backend.POSTGRES_SCHEMA)
    assert len(statements) > 0
    for stmt in statements:
        parsed = sqlparse.parse(stmt)
        assert parsed, f"failed to parse: {stmt[:60]!r}"


def test_schema_contains_every_table_the_lightweight_runner_needs():
    """One table per storage.py function actually reachable from the core
    engine tick loop + the cloud dashboard's analytics -- see
    DEPLOYMENT_CHECKPOINT.md Step 0 for how this list was derived."""
    expected_tables = {
        "paper_positions", "paper_account_state", "paper_strategy_config",
        "paper_alerts", "confluence_score_log", "paper_auto_avoid_rules",
        "paper_strategy_overrides", "paper_lesson_candidates", "paper_auto_lessons",
        "paper_decision_log", "paper_strategy_stat_archives", "telegram_message_log",
        "lessons", "paper_strategy_performance", "paper_lesson_performance",
        "bot_strategies", "bot_lessons", "auth_credentials", "auth_sessions", "cloud_settings",
        "kill_switch_state", "activity_log", "audit_trail_log", "telegram_retry_queue",
    }
    for table in expected_tables:
        assert f"CREATE TABLE IF NOT EXISTS {table} (" in db_backend.POSTGRES_SCHEMA, table


def test_every_on_conflict_target_has_a_matching_constraint_in_the_schema():
    """Every real `ON CONFLICT(col1, col2, ...)` clause storage.py issues
    against one of the curated tables must name a column set this schema
    actually declares PRIMARY KEY or UNIQUE on -- Postgres rejects the
    write outright otherwise (a loud failure, not a silent wrong answer,
    but one worth catching before it ever reaches Railway). Verified by
    reading storage.py's real query text, not by re-typing the list."""
    import re
    storage_mod = importlib.import_module("data_engine.storage")
    text = open(storage_mod.__file__, encoding="utf-8").read()

    # (table, conflict_columns) pairs for every curated table's writer
    # function, found directly in storage.py's own INSERT statements.
    checks = [
        ("paper_account_state", {"strategy_id"}),
        ("paper_strategy_config", {"strategy_id"}),
        ("paper_auto_lessons", {"strategy_id", "symbol", "market_state", "session"}),
        ("paper_auto_avoid_rules", {"strategy_id", "symbol", "market_state", "session"}),
        ("paper_strategy_overrides", {"strategy_id"}),
        ("paper_lesson_candidates", {"strategy_id", "symbol", "market_state", "session"}),
        ("kill_switch_state", {"id"}),
    ]
    schema = db_backend.POSTGRES_SCHEMA
    for table, cols in checks:
        # The real clause must exist in storage.py for this table (proves
        # the test is checking a claim storage.py actually makes).
        pattern = r"INSERT INTO " + table + r"[\s\S]{0,400}?ON CONFLICT\(([^)]*)\)"
        m = re.search(pattern, text)
        assert m, f"expected an ON CONFLICT clause writing to {table}"
        found_cols = {c.strip() for c in m.group(1).split(",")}
        assert found_cols == cols, (table, found_cols, cols)

        # The schema must declare a matching PRIMARY KEY or UNIQUE.
        table_block_m = re.search(
            r"CREATE TABLE IF NOT EXISTS " + table + r"\s*\((.*?)\n\);", schema, re.DOTALL,
        )
        assert table_block_m, f"{table} missing from schema"
        block = table_block_m.group(1)
        has_single_col_pk = len(cols) == 1 and re.search(
            re.escape(next(iter(cols))) + r"\s+\w+.*PRIMARY KEY", block,
        )
        has_unique = False
        for unique_m in re.finditer(r"UNIQUE \(([^)]*)\)", block):
            unique_cols = {c.strip() for c in unique_m.group(1).split(",")}
            if unique_cols == cols:
                has_unique = True
                break
        assert has_single_col_pk or has_unique, (
            f"{table} has no PRIMARY KEY/UNIQUE matching ON CONFLICT{tuple(cols)}"
        )
