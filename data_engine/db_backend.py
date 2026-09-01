"""Dual-backend database support: SQLite (the local laptop, unchanged
default) or PostgreSQL (the lightweight cloud runner), selected purely by
whether the DATABASE_URL environment variable is set.

This module is deliberately the ONLY new file storage.py depends on for
Postgres support -- storage.py's own 5000+ lines of query text (all written
with SQLite's "?" placeholders) are NOT rewritten. Instead, _PGConnection
below wraps a real psycopg2 connection so it accepts the exact same
"?"-placeholder SQL text and the exact same .execute(...).fetchone()/
.fetchall() calling convention sqlite3.Connection already provides --
every existing storage.py function works against either backend unchanged.

IMPORTANT SCOPE NOTE: only a curated set of tables (POSTGRES_SCHEMA below)
is created in Postgres -- exactly the tables the lightweight cloud runner's
paper trading + Telegram code path touches (see DEPLOYMENT_CHECKPOINT.md
for the full reasoning). The klines_1m / backtest_* / ai_* / evolution
governor tables that make the real local database 45+ GB are intentionally
NOT part of this schema -- the cloud database stays small by construction,
not by trimming data out of a bigger schema later.

If a storage.py function outside that curated set is ever called while
DATABASE_URL is set, Postgres will raise a normal "relation does not
exist" error -- loud and immediate, never a silent wrong answer.
"""

import os
import re

IS_POSTGRES = bool(os.environ.get("DATABASE_URL"))

_QUESTION_MARK_RE = re.compile(r"\?")


def _translate_placeholders(sql):
    """SQLite's "?" positional placeholder -> psycopg2's "%s". Simple
    text substitution is safe here: every query in this codebase builds
    SQL from fixed string literals (f-strings only ever interpolate
    trusted, hardcoded column/table names -- never user input), so a "?"
    appearing outside a placeholder position does not happen in practice."""
    return _QUESTION_MARK_RE.sub("%s", sql)


class _PGCursorResult:
    """Thin pass-through so callers can keep writing
    conn.execute(...).fetchone() / .fetchall() exactly as they do for
    sqlite3, without caring which backend is live."""

    def __init__(self, cursor):
        self._cursor = cursor

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def lastrowid(self):
        # psycopg2 has no sqlite3-style lastrowid. Nothing in the curated
        # table set's storage.py call sites relies on it (every INSERT
        # here either has an app-supplied TEXT primary key, or the caller
        # never reads .lastrowid back) -- surfaced as a clear error rather
        # than a silent None if that ever changes.
        raise AttributeError(
            "lastrowid is not available on Postgres -- use RETURNING id "
            "in the query, or an app-generated primary key, instead."
        )


class _PGConnection:
    """Wraps a psycopg2 connection to look enough like sqlite3.Connection
    for storage.py's existing call patterns: .execute(sql, params),
    .executemany(sql, seq_of_params), .executescript(sql), .commit(),
    .close()."""

    def __init__(self, raw_conn):
        self._conn = raw_conn

    def execute(self, sql, params=()):
        cur = self._conn.cursor()
        cur.execute(_translate_placeholders(sql), tuple(params))
        return _PGCursorResult(cur)

    def executemany(self, sql, seq_of_params):
        cur = self._conn.cursor()
        cur.executemany(_translate_placeholders(sql), [tuple(p) for p in seq_of_params])
        return _PGCursorResult(cur)

    def executescript(self, sql):
        """sqlite3-only method storage.py's init_db() calls with the full
        _SCHEMA string. Postgres init instead goes through
        init_postgres_schema() below (a hand-authored, curated schema) --
        this method existing at all is just so any incidental call site
        doesn't hit an AttributeError; it is not used on the Postgres path
        in practice."""
        cur = self._conn.cursor()
        cur.execute(sql)
        return _PGCursorResult(cur)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def get_postgres_conn():
    """Opens one real Postgres connection for DATABASE_URL. Called from
    storage.get_conn() -- same one-connection-per-call-then-close pattern
    already used for SQLite, so no separate pooling logic is needed for a
    lightweight runner's traffic level. Railway's internal Postgres
    connection string already includes sslmode as needed; nothing extra
    is added here."""
    import psycopg2

    raw = psycopg2.connect(os.environ["DATABASE_URL"])
    return _PGConnection(raw)


# --------------------------------------------------------------- schema

# Every column here was read directly off the real, fully-migrated local
# database via PRAGMA table_info (see DEPLOYMENT_CHECKPOINT.md) -- this is
# the CURRENT shape of each table, not the original CREATE TABLE plus a
# chain of ALTER TABLEs. A fresh Postgres database is created with exactly
# this final shape in one pass; none of storage.py's SQLite-specific
# `_migrate_*` functions (PRAGMA table_info, ALTER TABLE ADD COLUMN) ever
# need to run against Postgres, because there is no legacy shape to migrate
# FROM here.
#
# SQLite's INTEGER PRIMARY KEY (rowid alias, auto-incrementing) becomes
# Postgres's SERIAL PRIMARY KEY. A TEXT primary key (the app always
# generates its own id -- position ids, strategy ids, lesson ids) stays a
# plain TEXT PRIMARY KEY on both backends, unchanged. Every REAL/INTEGER/
# TEXT column type name is valid, unchanged, in Postgres too -- no type
# translation table is needed.
POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_positions (
    id TEXT PRIMARY KEY,
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL,
    stop_loss REAL,
    take_profit REAL,
    size REAL NOT NULL,
    risk_amount REAL,
    entry_time BIGINT NOT NULL,
    exit_time BIGINT,
    pnl REAL,
    pnl_pct REAL,
    exit_reason TEXT,
    entry_reason TEXT,
    strategy_id TEXT,
    strategy_name TEXT,
    strategy_version INTEGER,
    lesson_ids_json TEXT,
    confidence REAL,
    market_snapshot_json TEXT,
    tags_json TEXT,
    session TEXT,
    timeframe TEXT,
    market_state TEXT,
    lifecycle_json TEXT,
    reflection_json TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL,
    closed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_paper_positions_status_closed
    ON paper_positions(status, closed_at);

CREATE TABLE IF NOT EXISTS paper_account_state (
    strategy_id TEXT PRIMARY KEY,
    realized_pnl_total REAL NOT NULL DEFAULT 0.0,
    closed_count INTEGER NOT NULL DEFAULT 0,
    win_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS paper_strategy_config (
    strategy_id TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 1,
    priority INTEGER NOT NULL DEFAULT 5,
    supported_coins_json TEXT,
    supported_market_types_json TEXT,
    updated_at TEXT,
    paused INTEGER NOT NULL DEFAULT 0,
    paused_reason TEXT,
    paused_at TEXT,
    capital_multiplier REAL NOT NULL DEFAULT 1.0,
    capital_multiplier_reason TEXT,
    risk_pct_override REAL,
    max_open_trades_override INTEGER
);

CREATE TABLE IF NOT EXISTS paper_alerts (
    id SERIAL PRIMARY KEY,
    alert_type TEXT NOT NULL,
    strategy_id TEXT,
    strategy_name TEXT,
    message TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_paper_alerts_created ON paper_alerts(created_at DESC);

CREATE TABLE IF NOT EXISTS confluence_score_log (
    id SERIAL PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    position_id TEXT,
    confluence_ratio REAL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_confluence_log_strategy
    ON confluence_score_log(strategy_id, created_at DESC);

CREATE TABLE IF NOT EXISTS paper_auto_avoid_rules (
    id SERIAL PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    strategy_name TEXT,
    symbol TEXT NOT NULL,
    market_state TEXT NOT NULL,
    session TEXT NOT NULL,
    consecutive_losses INTEGER NOT NULL,
    reason TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    triggered_at TEXT NOT NULL,
    deactivated_at TEXT,
    UNIQUE (strategy_id, symbol, market_state, session)
);

CREATE TABLE IF NOT EXISTS paper_strategy_overrides (
    strategy_id TEXT PRIMARY KEY,
    manual_alert INTEGER NOT NULL DEFAULT 0,
    note TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS paper_lesson_candidates (
    id SERIAL PRIMARY KEY,
    strategy_id TEXT,
    strategy_name TEXT,
    symbol TEXT,
    market_state TEXT,
    session TEXT,
    pattern_description TEXT NOT NULL,
    sample_size INTEGER NOT NULL,
    win_rate REAL,
    total_pnl REAL,
    status TEXT NOT NULL DEFAULT 'flagged',
    created_at TEXT NOT NULL,
    UNIQUE (strategy_id, symbol, market_state, session)
);

CREATE TABLE IF NOT EXISTS paper_auto_lessons (
    id SERIAL PRIMARY KEY,
    strategy_id TEXT,
    strategy_name TEXT,
    symbol TEXT NOT NULL,
    market_state TEXT NOT NULL,
    session TEXT NOT NULL,
    influence TEXT NOT NULL,
    sample_size INTEGER NOT NULL,
    win_rate REAL NOT NULL,
    explanation TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    applied_at TEXT NOT NULL,
    deactivated_at TEXT,
    UNIQUE (strategy_id, symbol, market_state, session)
);

CREATE TABLE IF NOT EXISTS paper_decision_log (
    id SERIAL PRIMARY KEY,
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT,
    decision TEXT NOT NULL,
    reason TEXT,
    strategy_id TEXT,
    strategy_name TEXT,
    lesson_ids_json TEXT,
    confidence REAL,
    market_state TEXT,
    session TEXT,
    timeframe TEXT,
    position_id TEXT,
    market_snapshot_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_strategy_stat_archives (
    id SERIAL PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    archived_at TEXT NOT NULL,
    previous_realized_pnl_total REAL NOT NULL,
    previous_closed_count INTEGER NOT NULL,
    previous_win_count INTEGER NOT NULL,
    open_positions_left_running INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_paper_strategy_stat_archives_strategy
    ON paper_strategy_stat_archives(strategy_id, archived_at DESC);

CREATE TABLE IF NOT EXISTS telegram_message_log (
    id SERIAL PRIMARY KEY,
    position_id TEXT,
    strategy_id TEXT,
    strategy_name TEXT,
    trigger_type TEXT NOT NULL,
    message_text TEXT NOT NULL,
    success INTEGER NOT NULL,
    error TEXT,
    sent_at TEXT NOT NULL,
    explanation_text TEXT,
    quality_grade TEXT,
    grade_reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_telegram_log_sent_at ON telegram_message_log(sent_at DESC);

-- Empty on a fresh cloud database (lessons are hand-authored locally
-- today) -- exists purely so lesson_matcher.relevant_lessons() and
-- evolution.record_outcome()'s get_lesson() lookup have a real table to
-- query instead of erroring; both already handle "no rows" gracefully.
CREATE TABLE IF NOT EXISTS lessons (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT,
    priority TEXT NOT NULL DEFAULT 'Medium',
    status TEXT NOT NULL DEFAULT 'active',
    notes TEXT,
    apply_backtesting INTEGER NOT NULL DEFAULT 1,
    apply_paper_trading INTEGER NOT NULL DEFAULT 1,
    apply_evolution INTEGER NOT NULL DEFAULT 1,
    rule_type TEXT NOT NULL DEFAULT 'block_if_true',
    direction TEXT,
    conditions_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    tags_json TEXT,
    supported_market_types_json TEXT,
    supported_timeframes_json TEXT
);

CREATE TABLE IF NOT EXISTS paper_strategy_performance (
    strategy_id TEXT PRIMARY KEY,
    strategy_name TEXT,
    trades INTEGER NOT NULL DEFAULT 0,
    wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0,
    total_pnl REAL NOT NULL DEFAULT 0,
    avg_rr REAL,
    score REAL,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS paper_lesson_performance (
    lesson_id TEXT PRIMARY KEY,
    lesson_title TEXT,
    usage_count INTEGER NOT NULL DEFAULT 0,
    wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0,
    total_pnl REAL NOT NULL DEFAULT 0,
    confidence_avg REAL,
    score REAL,
    updated_at TEXT
);

-- Auto-generated by evolution_engine.generation_manager /
-- lesson_generator, triggered from paper_trading.position_manager on
-- every real trade close -- kept as its OWN small, ordinary tables, same
-- as local, rather than special-cased out. See DEPLOYMENT_CHECKPOINT.md
-- for why: skipping this call would mean editing position_manager.py (a
-- core, heavily-tested file this task's GLOBAL RULES say not to touch),
-- whereas provisioning its two small tables here keeps that file
-- completely unmodified for both backends. This is NOT the heavy,
-- continuously-running Evolution Engine tick/mutation loop (governor.py,
-- engine.py under evolution_engine/) -- that background process is not
-- imported or started anywhere in the lightweight cloud runner.
CREATE TABLE IF NOT EXISTS bot_strategies (
    id TEXT PRIMARY KEY,
    base_id TEXT NOT NULL,
    generation INTEGER NOT NULL DEFAULT 1,
    parent_id TEXT,
    name TEXT NOT NULL,
    config_json TEXT NOT NULL,
    dna_json TEXT,
    origin TEXT NOT NULL,
    made_with_ai INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    evolution_score REAL,
    score_breakdown_json TEXT,
    backtest_summary_json TEXT,
    mutation_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bot_lessons (
    id TEXT PRIMARY KEY,
    base_id TEXT NOT NULL,
    generation INTEGER NOT NULL DEFAULT 1,
    parent_id TEXT,
    title TEXT NOT NULL,
    category TEXT,
    description TEXT,
    derived_from_json TEXT NOT NULL,
    conditions_json TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    confidence REAL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def init_postgres_schema(conn):
    """Called once from storage.init_db() when DATABASE_URL is set --
    creates the curated table set above (all IF NOT EXISTS, safe to call
    on every startup, same idempotency guarantee init_db() already gives
    the SQLite path)."""
    conn.executescript(POSTGRES_SCHEMA)
