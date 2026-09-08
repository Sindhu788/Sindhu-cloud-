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
    is added here.

    connect_timeout=10: without it, psycopg2.connect() has NO timeout at
    all and can hang for minutes if Postgres is briefly unreachable (e.g.
    right after the database was created, or a transient network blip) --
    confirmed live (Priority-15 Item 1) as the cause of a total cloud
    outage: storage.init_db() calls this from cloud_runtime.app's lifespan
    BEFORE the app starts serving anything, so a hung connect() there
    blocked literally every endpoint, including /health, which is coded
    to bypass all other checks. Failing fast after 10s means a genuinely
    unreachable database surfaces as a clear, loggable connection error
    instead of an indefinite, silent hang."""
    import psycopg2

    raw = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=10)
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
-- Pre-existing gap found while building the Grand Feature Expansion's
-- Audit Trail (Phase 1 Feature 3): sindhu_web/sync.py notify() -- called
-- unconditionally by paper_trading start/stop and several other routes
-- already mounted on the cloud runner -- writes to activity_log via
-- storage.log_activity(), but this table was never part of the curated
-- cloud schema. That means clicking Start/Stop Engine (or any other
-- notify()-calling action) on a real Postgres-connected cloud deployment
-- would have raised "relation activity_log does not exist" the moment it
-- ran. Fixed here by adding it for real (not working around it) -- same
-- schema as the local SQLite table, same 500-row cap logic in
-- log_activity() works identically against Postgres.
CREATE TABLE IF NOT EXISTS activity_log (
    id SERIAL PRIMARY KEY,
    entity TEXT NOT NULL,
    action TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- Grand Feature Expansion, Phase 5 Feature 1: Coin Blacklist. The tick
-- loop (resumed on cloud startup too -- see cloud_runtime/app.py's
-- resume_engine_on_startup) checks this before coin_filter.shortlist(),
-- so it must exist on Postgres wherever the engine can actually run.
CREATE TABLE IF NOT EXISTS paper_coin_blacklist (
    symbol TEXT PRIMARY KEY,
    reason TEXT,
    added_at TEXT NOT NULL
);

-- Confirmed live on Render, 2026-09-08: custom_alerts.sweep_custom_alert_rules()
-- runs every tick from paper_trading/engine.py and hit
-- UndefinedTable('relation "custom_alert_rules" does not exist') because this
-- table -- present in the SQLite schema (data_engine/storage.py) -- was never
-- added to the curated Postgres schema. Same mistake as paper_coin_blacklist
-- and paper_strategy_groups above; fixed here the same way.
CREATE TABLE IF NOT EXISTS custom_alert_rules (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    metric TEXT NOT NULL,
    strategy_id TEXT,
    comparison TEXT NOT NULL,
    threshold REAL NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    last_triggered_at TEXT
);

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
    closed_at TEXT,
    -- Grand Feature Expansion, Phase 3 Feature 8 (MAE/MFE): mirrors the
    -- local SQLite schema exactly (see data_engine/storage.py).
    lowest_price_seen REAL,
    highest_price_seen REAL
);
CREATE INDEX IF NOT EXISTS idx_paper_positions_status_closed
    ON paper_positions(status, closed_at);

-- Grand Feature Expansion, Phase 3 Feature 8 (MAE/MFE): unlike SQLite
-- (data_engine/storage.py's own _migrate_paper_positions_excursion_columns,
-- needed because SQLite has no "ADD COLUMN IF NOT EXISTS"), Postgres
-- supports it natively -- so this heals an ALREADY-LIVE cloud database
-- (which already has this table, so the CREATE TABLE above was a no-op
-- for it) the same way on every startup, no separate migration function
-- needed. Backfill is idempotent -- only ever touches rows still NULL.
ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS lowest_price_seen REAL;
ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS highest_price_seen REAL;
UPDATE paper_positions SET lowest_price_seen = entry_price, highest_price_seen = entry_price
    WHERE lowest_price_seen IS NULL;

-- Grand Feature Expansion, Phase 4 Feature 8 (Trade Annotation): same
-- always-safe idempotent healing pattern as the MAE/MFE columns above.
ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS user_note TEXT;

CREATE TABLE IF NOT EXISTS paper_account_state (
    strategy_id TEXT PRIMARY KEY,
    realized_pnl_total REAL NOT NULL DEFAULT 0.0,
    closed_count INTEGER NOT NULL DEFAULT 0,
    win_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT
);

-- CEO Task 3 (Independent Paper Trading Groups), 2026-09-08: same table
-- data_engine/storage.py's SQLite schema declares -- added here too so
-- this project never repeats the exact mistake that crashed the last two
-- deploys (a table that exists in the SQLite schema but is missing from
-- this curated Postgres one; see server_restart_log's own comment below
-- for that incident). Just a group label per strategy -- balances/PnL
-- keep being tracked in the existing paper_account_state/
-- paper_strategy_performance rows above, summed per group at read time.
CREATE TABLE IF NOT EXISTS paper_strategy_groups (
    strategy_id TEXT PRIMARY KEY,
    group_key TEXT NOT NULL,
    assigned_at TEXT NOT NULL,
    auto_assigned INTEGER NOT NULL DEFAULT 1
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
    max_open_trades_override INTEGER,
    htf_confluence_filter_enabled INTEGER,
    volume_spike_filter_enabled INTEGER,
    trailing_stop_enabled INTEGER
);

-- Master Task 6, 2.3/2.4/2.5: heals an ALREADY-LIVE cloud database the
-- same way the MAE/MFE columns above do -- see that comment for why this
-- is needed on Postgres (no ADD COLUMN IF NOT EXISTS on SQLite) even
-- though the CREATE TABLE above already lists these columns for a FRESH
-- database.
ALTER TABLE paper_strategy_config ADD COLUMN IF NOT EXISTS htf_confluence_filter_enabled INTEGER;
ALTER TABLE paper_strategy_config ADD COLUMN IF NOT EXISTS volume_spike_filter_enabled INTEGER;
ALTER TABLE paper_strategy_config ADD COLUMN IF NOT EXISTS trailing_stop_enabled INTEGER;

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

-- Master Task 5, Part 1.5: Near-Miss Log (see storage.py for full context).
CREATE TABLE IF NOT EXISTS near_miss_log (
    id SERIAL PRIMARY KEY,
    position_id TEXT NOT NULL UNIQUE,
    strategy_id TEXT,
    strategy_name TEXT,
    symbol TEXT,
    confluence_ratio REAL,
    confluence_passed INTEGER,
    confluence_total INTEGER,
    confluence_required_ratio REAL,
    confluence_required_count INTEGER,
    pattern_status TEXT,
    pattern_trades INTEGER,
    pattern_required INTEGER,
    pattern_win_rate_pct REAL,
    live_pnl REAL,
    reason TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_near_miss_log_created ON near_miss_log(created_at DESC);

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

-- Grand Feature Expansion, Phase 2 Feature 11: Delivery Retry Queue.
-- Mirrors the local SQLite schema exactly (see data_engine/storage.py) --
-- telegram_bot.py (which writes here) runs on the cloud runner too.
CREATE TABLE IF NOT EXISTS telegram_retry_queue (
    id SERIAL PRIMARY KEY,
    position_id TEXT NOT NULL,
    trigger_type TEXT NOT NULL,
    high_confidence INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL,
    last_attempt_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_telegram_retry_status ON telegram_retry_queue(status);

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

-- Login credentials + sessions (sindhu_web/auth.py). On the local laptop
-- these live in data/config/auth_credentials.json + auth_sessions.json --
-- fine there because the local disk is permanent. Render's free tier
-- filesystem is EPHEMERAL: it is wiped on every restart, redeploy, and
-- sleep/wake cycle, so a cloud deploy that kept using those JSON files lost
-- its login every time the host recycled, forcing "first-time setup" again
-- even though nothing was actually wrong. Moving them into this same
-- curated Postgres database (which already backs paper_positions etc. and
-- genuinely survives restarts) fixes that; auth.py branches on
-- db_backend.IS_POSTGRES exactly like every other dual-backend call site.
CREATE TABLE IF NOT EXISTS auth_credentials (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL,
    salt TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    token TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

-- Same ephemeral-filesystem problem as auth_credentials above, for the two
-- operational settings files a CEO actually toggles from the dashboard:
-- paper_trading/config.py's paper_trading_settings.json (Dry Run Mode,
-- engine on/off, the 5-open-trades-per-strategy default, etc.) and
-- paper_trading/telegram_bot.py's telegram_settings.json (auto-send
-- on/off, confidence thresholds, Signal Freshness Gate). Flipping "Dry
-- Run Mode" off on a Render free instance previously would not survive
-- the next restart/redeploy/sleep-wake -- it would silently revert to the
-- conservative default (dry_run: True) with no visible error, exactly the
-- same failure shape Part 1 fixed for login credentials. One generic
-- key/value table (rather than one bespoke table per settings file, which
-- would repeat auth_credentials' shape for no reason -- these are plain
-- JSON blobs, not queried by column) covers both, and any future settings
-- file that needs the same treatment, without another schema change.
CREATE TABLE IF NOT EXISTS cloud_settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Grand Feature Expansion, Phase 1 Feature 1: Kill-Switch. Mirrors the
-- local SQLite schema exactly (see data_engine/storage.py) -- the cloud
-- runner trades too, so it needs the same global emergency-stop state.
CREATE TABLE IF NOT EXISTS kill_switch_state (
    id INTEGER PRIMARY KEY,
    active INTEGER NOT NULL DEFAULT 0,
    reason TEXT,
    close_positions INTEGER NOT NULL DEFAULT 0,
    activated_at TEXT,
    activated_by TEXT,
    deactivated_at TEXT,
    deactivated_by TEXT,
    activation_count INTEGER NOT NULL DEFAULT 0
);

-- Grand Feature Expansion, Phase 1 Feature 3: Audit Trail. sync.notify()
-- (sindhu_web/sync.py) writes here on every call and IS reachable from the
-- cloud runner (paper_trading start/stop, telegram settings, etc. all call
-- it) -- this table must exist in Postgres or every one of those calls
-- would raise "relation does not exist" the moment anything notifies.
-- Never pruned, unlike activity_log (see storage.py's record_audit_event).
CREATE TABLE IF NOT EXISTS audit_trail_log (
    id SERIAL PRIMARY KEY,
    entity TEXT NOT NULL,
    action TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL
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

-- Master Task 3, Phase 2.9: Multiple Simultaneous Challenges. Mirrors the
-- local SQLite schema exactly (see data_engine/storage.py) -- Challenge
-- Mode already runs identically on the cloud deploy (challenge_mode.py's
-- own cloud_settings dual-write), so this table must exist here too.
CREATE TABLE IF NOT EXISTS challenges (
    id TEXT PRIMARY KEY,
    label TEXT,
    start_amount REAL NOT NULL,
    target_amount REAL NOT NULL,
    timeframe_type TEXT NOT NULL DEFAULT 'custom',
    days INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    scope_strategy_id TEXT,
    scope_symbol TEXT,
    baseline_win_rate_pct REAL,
    telegram_report_enabled INTEGER NOT NULL DEFAULT 0,
    compounding INTEGER NOT NULL DEFAULT 1,
    archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS challenge_achievability_snapshots (
    id SERIAL PRIMARY KEY,
    challenge_id TEXT NOT NULL,
    achievability_score REAL,
    recorded_at TEXT NOT NULL
);

-- Grand Master Prompt Phase 3.13 (Restart Analytics): record_startup() in
-- sindhu_web/api/system.py calls storage.record_server_restart()
-- UNCONDITIONALLY and SYNCHRONOUSLY from cloud_runtime/app.py's lifespan,
-- before the app finishes starting -- exactly the same failure shape as
-- activity_log above (a table the curated schema forgot, hit on every
-- single boot instead of only on one route). Missing this table crashed
-- the whole cloud deploy's startup, not just one endpoint.
CREATE TABLE IF NOT EXISTS server_restart_log (
    id SERIAL PRIMARY KEY,
    deployment TEXT NOT NULL,
    started_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_server_restart_log_deployment ON server_restart_log(deployment, started_at DESC);

-- Grand Master Prompt Phase 2.4 (Auto-Downgrade Rule): read/written from
-- paper_trading/auto_downgrade.py's background thread, which runs on this
-- cloud runner (started from cloud_runtime/app.py's lifespan).
CREATE TABLE IF NOT EXISTS paper_downgrade_state (
    strategy_id TEXT PRIMARY KEY,
    downgraded INTEGER NOT NULL DEFAULT 0,
    profit_factor REAL,
    sample_size INTEGER NOT NULL DEFAULT 0,
    reason TEXT,
    updated_at TEXT NOT NULL
);

-- Grand Master Prompt Phase 3.6 (Coin Manager): paper_trading_api.router is
-- fully mounted on this cloud runner, so its pin/demote endpoints (backed
-- by paper_trading/coin_priority.py) must have this table on Postgres too.
CREATE TABLE IF NOT EXISTS paper_coin_priority (
    symbol TEXT PRIMARY KEY,
    priority TEXT NOT NULL CHECK (priority IN ('pinned', 'demoted')),
    reason TEXT,
    added_at TEXT NOT NULL
);

-- Grand Master Prompt Phase 4.6 (Goal System): paper_trading_api.router's
-- goals endpoints (backed by paper_trading/goal_system.py) are reachable
-- on this cloud runner the same way.
CREATE TABLE IF NOT EXISTS user_goals (
    id TEXT PRIMARY KEY,
    metric TEXT NOT NULL,
    target_value REAL NOT NULL,
    comparison TEXT NOT NULL CHECK (comparison IN ('gte', 'lte')),
    scope_strategy_id TEXT,
    label TEXT,
    archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    achieved_at TEXT
);
"""


def init_postgres_schema(conn):
    """Called once from storage.init_db() when DATABASE_URL is set --
    creates the curated table set above (all IF NOT EXISTS, safe to call
    on every startup, same idempotency guarantee init_db() already gives
    the SQLite path)."""
    conn.executescript(POSTGRES_SCHEMA)
