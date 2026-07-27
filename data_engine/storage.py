import json
import sqlite3
import os
import statistics
from contextlib import contextmanager

from data_engine.paths import DB_PATH, DATABASE_DIR, ensure_folders

DEFAULT_EXCHANGE = "binance"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS symbols (
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    added_at TEXT NOT NULL,
    PRIMARY KEY (exchange, symbol)
);

CREATE TABLE IF NOT EXISTS klines_1m (
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    open_time INTEGER NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,
    close_time INTEGER NOT NULL,
    quote_volume REAL NOT NULL,
    trades INTEGER NOT NULL,
    PRIMARY KEY (exchange, symbol, open_time)
);

CREATE TABLE IF NOT EXISTS download_progress (
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    last_open_time INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',
    updated_at TEXT,
    PRIMARY KEY (exchange, symbol)
);

CREATE TABLE IF NOT EXISTS strategies (
    name TEXT PRIMARY KEY,
    file_path TEXT NOT NULL,
    added_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS backtest_batches (
    batch_id TEXT PRIMARY KEY,
    strategy_name TEXT NOT NULL,
    exchange TEXT NOT NULL,
    settings_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    created_at TEXT NOT NULL,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS backtest_results (
    batch_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    metrics_json TEXT,
    completed_at TEXT,
    PRIMARY KEY (batch_id, symbol, timeframe)
);

CREATE TABLE IF NOT EXISTS backtest_trades (
    batch_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    trade_num INTEGER NOT NULL,
    side TEXT NOT NULL,
    entry_time INTEGER NOT NULL,
    entry_price REAL NOT NULL,
    exit_time INTEGER,
    exit_price REAL,
    size REAL NOT NULL,
    pnl REAL,
    pnl_pct REAL,
    exit_reason TEXT,
    stop_loss REAL,
    take_profit REAL,
    risk_amount REAL,
    reward_amount REAL,
    entry_reason TEXT,
    PRIMARY KEY (batch_id, symbol, timeframe, trade_num)
);

-- This table reaches tens of millions of rows (15.6M measured). Lookups by
-- batch_id are already served by the primary key above (batch_id leads it),
-- but search_trades() -- which backs the dashboard's Global Search box on
-- EVERY page -- does "WHERE symbol LIKE ? ORDER BY entry_time DESC LIMIT n".
-- Without an index on entry_time that planned as "SCAN backtest_trades +
-- USE TEMP B-TREE FOR ORDER BY": a full 15.6M-row scan plus a full sort,
-- measured 25.6 SECONDS to return 20 rows. With this index SQLite walks
-- newest-first and stops as soon as the LIMIT is satisfied.
CREATE INDEX IF NOT EXISTS idx_backtest_trades_entry_time ON backtest_trades(entry_time DESC);

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
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lesson_applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lesson_id TEXT NOT NULL,
    batch_id TEXT,
    symbol TEXT,
    timeframe TEXT,
    applied_at TEXT NOT NULL,
    outcome TEXT NOT NULL
);

-- This table grows one row per lesson per bar checked during backtests --
-- millions of rows in practice. get_lesson_stats()/get_lesson_stats_bulk()
-- filter by lesson_id, and get_batch_lesson_stats() filters by batch_id;
-- without these, both are full-table scans that get slower as the table
-- grows (measured: 90+s for a lesson-stats pass at 3.6M rows). Additive,
-- CREATE INDEX IF NOT EXISTS is safe to run on every startup.
CREATE INDEX IF NOT EXISTS idx_lesson_applications_lesson_id ON lesson_applications(lesson_id);
CREATE INDEX IF NOT EXISTS idx_lesson_applications_batch_id ON lesson_applications(batch_id);

-- Running per-lesson totals, kept in sync incrementally by
-- record_lesson_application()/record_lesson_applications_bulk() every time
-- a row is written to lesson_applications. Even WITH the index above,
-- COUNT(*)/SUM(...) over a lesson's full history still means reading every
-- one of its (tens of thousands of) matching rows -- measured 5-11s for
-- all lessons combined even with the index, because SQLite still has to
-- walk every matching index entry to aggregate. This table turns that into
-- a single O(1) primary-key lookup per lesson: the aggregate is computed
-- once, incrementally, at write time, not recomputed from scratch on every
-- Knowledge page load. _migrate_lesson_stats_summary_backfill() seeds this
-- once from existing history for anyone upgrading from before this table
-- existed.
CREATE TABLE IF NOT EXISTS lesson_stats_summary (
    lesson_id TEXT PRIMARY KEY,
    times_used INTEGER NOT NULL DEFAULT 0,
    trades_approved INTEGER NOT NULL DEFAULT 0,
    trades_rejected INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity TEXT NOT NULL,
    action TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL
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
    entry_time INTEGER NOT NULL,
    exit_time INTEGER,
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

-- One row per strategy (or the synthetic "__lessons__" key for trades not
-- tied to any specific strategy) -- each strategy trades its own
-- independent book (balance, PnL, open-position cap) once multiple
-- strategies can run in Paper Trading simultaneously; see
-- _migrate_paper_account_state_per_strategy() for the one-time conversion
-- from the old single-row-shared-by-everyone schema.
CREATE TABLE IF NOT EXISTS paper_account_state (
    strategy_id TEXT PRIMARY KEY,
    realized_pnl_total REAL NOT NULL DEFAULT 0.0,
    closed_count INTEGER NOT NULL DEFAULT 0,
    win_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS paper_decision_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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

-- Telegram Integration: permanent audit trail of every message sent or
-- attempted (manual or automatic), so nothing is ever sent silently.
CREATE TABLE IF NOT EXISTS telegram_message_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id TEXT,
    strategy_id TEXT,
    strategy_name TEXT,
    trigger_type TEXT NOT NULL,
    message_text TEXT NOT NULL,
    success INTEGER NOT NULL,
    error TEXT,
    sent_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_telegram_log_sent_at ON telegram_message_log(sent_at DESC);

-- Weekly Auto-Report (Dashboard Consolidation Group, item 7): one row per
-- generated report, permanently stored so past reports stay reviewable.
CREATE TABLE IF NOT EXISTS paper_weekly_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    report_json TEXT NOT NULL,
    report_text TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- Strategy Graveyard (Confidence & Signal Quality Group, item 9): a
-- permanent, never-deleted record of why a strategy was effectively
-- abandoned, so a similar future import can be warned it resembles
-- something that already failed.
CREATE TABLE IF NOT EXISTS strategy_graveyard (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id TEXT NOT NULL,
    strategy_name TEXT NOT NULL,
    reason_category TEXT NOT NULL,
    reason_detail TEXT NOT NULL,
    concepts_used_json TEXT,
    buried_at TEXT NOT NULL
);

-- Pattern-Based Auto-Avoid (self-learning, active): one row per exact
-- (strategy, symbol, market_state, session) pattern that hit the
-- consecutive-loss threshold. Presence of an active=1 row is the veto
-- itself -- checked by paper_trading.auto_avoid before a new entry opens.
-- Never deletes the strategy or blocks other patterns for it, and a person
-- can deactivate any row from the dashboard (reversible, fully audited).
CREATE TABLE IF NOT EXISTS paper_auto_avoid_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    UNIQUE(strategy_id, symbol, market_state, session)
);

-- Lesson Auto-Apply (self-learning, active): a paper_lesson_candidate that
-- accumulated enough evidence gets promoted here as a live, reversible soft
-- filter (confidence nudge, never a hard block) -- see
-- paper_trading.lesson_auto_apply. influence is "boost" (strongly winning
-- pattern) or "avoid" (strongly losing pattern, softer than the streak-based
-- auto-avoid rule above since it triggers on win-rate evidence, not a live
-- streak).
CREATE TABLE IF NOT EXISTS paper_auto_lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    UNIQUE(strategy_id, symbol, market_state, session)
);

CREATE TABLE IF NOT EXISTS paper_strategy_config (
    strategy_id TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 1,
    priority INTEGER NOT NULL DEFAULT 5,
    supported_coins_json TEXT,
    supported_market_types_json TEXT,
    paused INTEGER NOT NULL DEFAULT 0,
    paused_reason TEXT,
    paused_at TEXT,
    updated_at TEXT
);

-- Manual Override: a human can flag a strategy for a Telegram alert
-- regardless of what its automatic score says. This table only records
-- the flag (and who/why) -- it never touches paper_strategy_config
-- (enabled/priority/coin routing), trade execution, or scoring.
CREATE TABLE IF NOT EXISTS paper_strategy_overrides (
    strategy_id TEXT PRIMARY KEY,
    manual_alert INTEGER NOT NULL DEFAULT 0,
    note TEXT,
    updated_at TEXT
);

-- Real-Time Alert / Drawdown Alert history -- computed fresh each time
-- paper_trading.alerts is asked to check (see that module), persisted here
-- only so the UI has a short recent history instead of alerts vanishing
-- the instant nobody happens to be polling. Never read by the trading
-- engine itself -- purely a reporting/notification trail.
CREATE TABLE IF NOT EXISTS paper_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_type TEXT NOT NULL,
    strategy_id TEXT,
    strategy_name TEXT,
    message TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_paper_alerts_created ON paper_alerts(created_at DESC);

-- Lesson Candidate Auto-Flagging (self-learning foundation, Group 3):
-- repeated patterns detected in closed trades get flagged here for human
-- review. Never auto-applied to any strategy or lesson -- status stays
-- 'flagged' until a person acts on it elsewhere.
CREATE TABLE IF NOT EXISTS paper_lesson_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    UNIQUE(strategy_id, symbol, market_state, session)
);

CREATE TABLE IF NOT EXISTS compiled_documents (
    id TEXT PRIMARY KEY,
    title TEXT,
    source_type TEXT,
    doc_type TEXT NOT NULL,
    classification_confidence REAL,
    status TEXT NOT NULL,
    raw_text TEXT,
    sections_json TEXT,
    strategy_ids_json TEXT,
    lesson_ids_json TEXT,
    concepts_json TEXT,
    unresolved_json TEXT,
    clarification_notes_json TEXT,
    tags_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge_concepts (
    canonical_name TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    aliases_json TEXT,
    usage_count INTEGER NOT NULL DEFAULT 0,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge_relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_type TEXT NOT NULL,
    from_id TEXT NOT NULL,
    to_type TEXT NOT NULL,
    to_id TEXT NOT NULL,
    relation TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS backtest_condition_reports (
    batch_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    report_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (batch_id, symbol, timeframe)
);

CREATE TABLE IF NOT EXISTS ai_usage_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    model TEXT,
    endpoint TEXT NOT NULL,
    status TEXT NOT NULL,
    tokens_in INTEGER,
    tokens_out INTEGER,
    latency_ms INTEGER,
    error_message TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_import_queue (
    id TEXT PRIMARY KEY,
    title TEXT,
    source_hint TEXT,
    filename TEXT,
    raw_text TEXT NOT NULL,
    use_ai INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'pending',
    result_doc_id TEXT,
    ai_assisted INTEGER,
    ai_provider TEXT,
    error_message TEXT,
    processing_time_ms INTEGER,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS ai_dictionary_entries (
    canonical_name TEXT PRIMARY KEY,
    definition TEXT,
    keywords_json TEXT,
    category TEXT,
    source_doc_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_import_cache (
    content_hash TEXT PRIMARY KEY,
    ai_result_json TEXT NOT NULL,
    provider TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS strategy_optimizations (
    id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    original_batch_id TEXT NOT NULL,
    optimized_batch_id TEXT,
    winner TEXT NOT NULL,
    params_changed_json TEXT,
    candidates_tried_json TEXT,
    created_at TEXT NOT NULL
);

-- Durable checkpoint for the Automation Pipeline (import -> backtest ->
-- optimize -> compare -> paper trading). job_manager's own Job objects are
-- in-memory only and vanish on restart -- this row is what lets the server
-- tell, after an abrupt restart, whether a pipeline was still running when
-- it went down, and if so, resume it from the last safely-completed stage
-- instead of leaving it stuck "running" forever or silently forgetting it.
-- status='running' rows found at startup are exactly the ones that were
-- interrupted (a clean finish always sets status to completed/stopped/failed
-- before the row is left alone).
CREATE TABLE IF NOT EXISTS pipeline_jobs (
    job_id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    strategy_name TEXT,
    symbols_json TEXT,
    status TEXT NOT NULL,
    stage TEXT,
    checkpoint_json TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Phase 7A: Evolution Core Engine + SINDHU Strategy Generator. Every table
-- below is BOT-owned storage, physically separate from strategy_library's
-- user-owned folder storage and the user-authored `lessons` table -- this
-- is what makes the A.9 hard safety constraint ("Evolution may NEVER modify
-- user-imported strategies or user-written lessons") a structural guarantee
-- rather than a behavioral promise: there is no code path from
-- evolution_engine/sindhu_strategy into strategy_library's CRUD or the
-- lessons table at all, so it is not merely avoided, it is unreachable.
CREATE TABLE IF NOT EXISTS bot_strategies (
    id TEXT PRIMARY KEY,                   -- e.g. "BOT_S101_G3"
    base_id TEXT NOT NULL,                 -- e.g. "BOT_S101", shared by every generation in this lineage
    generation INTEGER NOT NULL DEFAULT 1,
    parent_id TEXT,                        -- previous generation's id, NULL for generation 1
    name TEXT NOT NULL,
    config_json TEXT NOT NULL,             -- StrategyConfig.to_dict()
    dna_json TEXT,                         -- DNA block tags this strategy is built from (evolution_engine/dna.py)
    origin TEXT NOT NULL,                  -- "evolution_mutation" | "sindhu_ai" | "sindhu_deterministic"
    made_with_ai INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active', -- "active" | "archived" -- rows are never deleted, only archived
    evolution_score REAL,
    score_breakdown_json TEXT,
    backtest_summary_json TEXT,
    mutation_reason TEXT,                  -- traceable: the exact comparison/stat that produced this generation
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bot_lessons (
    id TEXT PRIMARY KEY,                   -- e.g. "BOT_L004_G2"
    base_id TEXT NOT NULL,
    generation INTEGER NOT NULL DEFAULT 1,
    parent_id TEXT,
    title TEXT NOT NULL,
    category TEXT,
    description TEXT,
    derived_from_json TEXT NOT NULL,       -- exact source stats: {strategy_id, coin, session, metric, value, sample_size, ...}
    conditions_json TEXT,
    status TEXT NOT NULL DEFAULT 'active', -- rows are never deleted, only archived
    confidence REAL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evolution_jobs (
    job_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    stage TEXT,
    checkpoint_json TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS champion_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,   -- strategy | lesson | coin | session | timeframe | market_condition | generation
    value TEXT NOT NULL,      -- winning id/name
    score REAL,
    details_json TEXT,
    computed_at TEXT NOT NULL
);

-- Append-only: recomputing champions inserts a new row per category rather
-- than overwriting, so history is never lost -- "current" champion is just
-- the most recent row for that category (see get_current_champion below).
CREATE TABLE IF NOT EXISTS knowledge_versions (
    version INTEGER PRIMARY KEY AUTOINCREMENT,
    reason TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- Append-only ledger, one row per calendar date. Hard architectural limiter
-- for B.2 ("exactly 1 AI call per daily generation cycle"): reserving the
-- AI slot is a single guarded UPDATE (ai_calls_used=0 -> 1) that can only
-- ever succeed once per date, the same way ai_import_cache prevents a
-- repeat AI call for an already-seen document elsewhere in this system.
CREATE TABLE IF NOT EXISTS daily_generation_log (
    date TEXT PRIMARY KEY,   -- "YYYY-MM-DD"
    ai_calls_used INTEGER NOT NULL DEFAULT 0,
    candidates_generated INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
"""

_COMPILED_DOCUMENT_V6_COLUMNS = {
    "hidden_rules_json": "TEXT",
    "psychology_notes_json": "TEXT",
    "deep_knowledge_json": "TEXT",
}


def _migrate_compiled_document_v6_columns(conn):
    """AI Knowledge Learning Engine (v6): a compiled document can now carry
    AI-inferred hidden rules (rule/confidence/reason/evidence), extracted
    psychology notes, and the raw deep-understanding payload for audit --
    additive columns only, existing rows default to NULL/empty."""
    existing = {r[0] for r in
                conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if "compiled_documents" not in existing:
        return
    have_columns = {r[1] for r in conn.execute("PRAGMA table_info(compiled_documents)").fetchall()}
    for col, col_type in _COMPILED_DOCUMENT_V6_COLUMNS.items():
        if col not in have_columns:
            conn.execute(f"ALTER TABLE compiled_documents ADD COLUMN {col} {col_type}")


_AI_DICTIONARY_V6_COLUMNS = {
    "aliases_json": "TEXT",
    "examples_json": "TEXT",
    "related_concepts_json": "TEXT",
    "usage_notes": "TEXT",
}


_AI_IMPORT_QUEUE_V6_COLUMNS = {
    "input_kind": "TEXT NOT NULL DEFAULT 'text'",
}

_AI_IMPORT_QUEUE_CONTENT_TYPE_COLUMNS = {
    "content_type": "TEXT",
}

_AI_IMPORT_CACHE_V8_COLUMNS = {
    "ai_result_json": "TEXT",
    "provider": "TEXT",
}


def _migrate_ai_import_cache_v8_columns(conn):
    """v8: the pre-AI dedup cache initially stored a compiled_document_id
    pointer; redesigned to store the AI's structured result directly so a
    cache hit can still go through the normal build/save/dedupe path
    without ever re-calling AI. Additive-only -- any pre-v8 rows (from
    development only, never real CEO data) simply have NULL ai_result_json
    and are treated as a miss by get_ai_import_cache()."""
    existing = {r[0] for r in
                conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if "ai_import_cache" not in existing:
        return
    have_columns = {r[1] for r in conn.execute("PRAGMA table_info(ai_import_cache)").fetchall()}
    for col, col_type in _AI_IMPORT_CACHE_V8_COLUMNS.items():
        if col not in have_columns:
            conn.execute(f"ALTER TABLE ai_import_cache ADD COLUMN {col} {col_type}")


_BACKTEST_BATCH_NEW_COLUMNS = {
    "display_name": "TEXT",
}


_PAPER_STRATEGY_CONFIG_PAUSE_COLUMNS = {
    "paused": "INTEGER NOT NULL DEFAULT 0",
    "paused_reason": "TEXT",
    "paused_at": "TEXT",
}


def _migrate_paper_strategy_config_pause_columns(conn):
    """Drawdown Protection Engine: additive columns on an existing
    paper_strategy_config table (CREATE TABLE IF NOT EXISTS is a no-op once
    the table already exists from before this feature)."""
    existing = {r[0] for r in
                conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if "paper_strategy_config" not in existing:
        return
    have_columns = {r[1] for r in conn.execute("PRAGMA table_info(paper_strategy_config)").fetchall()}
    for col, col_type in _PAPER_STRATEGY_CONFIG_PAUSE_COLUMNS.items():
        if col not in have_columns:
            conn.execute(f"ALTER TABLE paper_strategy_config ADD COLUMN {col} {col_type}")


def _migrate_backtest_batch_columns(conn):
    """A saved batch was only ever identified by strategy_name + timestamp
    -- display_name is a purely cosmetic, optional rename the CEO can set
    from the Backtest History page (falls back to strategy_name wherever
    it's NULL). Additive-only, existing rows default to NULL."""
    existing = {r[0] for r in
                conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if "backtest_batches" not in existing:
        return
    have_columns = {r[1] for r in conn.execute("PRAGMA table_info(backtest_batches)").fetchall()}
    for col, col_type in _BACKTEST_BATCH_NEW_COLUMNS.items():
        if col not in have_columns:
            conn.execute(f"ALTER TABLE backtest_batches ADD COLUMN {col} {col_type}")


def _migrate_ai_import_queue_v6_columns(conn):
    """AI Knowledge Learning Engine (v6): a queued item can now be a YouTube
    URL instead of pasted/uploaded text -- additive column only, existing
    rows default to 'text' (unchanged behavior)."""
    existing = {r[0] for r in
                conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if "ai_import_queue" not in existing:
        return
    have_columns = {r[1] for r in conn.execute("PRAGMA table_info(ai_import_queue)").fetchall()}
    for col, col_type in _AI_IMPORT_QUEUE_V6_COLUMNS.items():
        if col not in have_columns:
            conn.execute(f"ALTER TABLE ai_import_queue ADD COLUMN {col} {col_type}")


def _migrate_ai_import_queue_content_type_column(conn):
    """Part 2 (explicit Strategy/Lesson/Mixed selector): the user's choice
    at queue-time needs to survive until the worker thread actually
    processes the item, so it's a persisted column, not just an in-memory
    call argument. Additive-only, existing rows default to NULL (treated
    as "mixed"/unspecified -- unchanged old behavior)."""
    existing = {r[0] for r in
                conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if "ai_import_queue" not in existing:
        return
    have_columns = {r[1] for r in conn.execute("PRAGMA table_info(ai_import_queue)").fetchall()}
    for col, col_type in _AI_IMPORT_QUEUE_CONTENT_TYPE_COLUMNS.items():
        if col not in have_columns:
            conn.execute(f"ALTER TABLE ai_import_queue ADD COLUMN {col} {col_type}")


def _migrate_lesson_stats_summary_backfill(conn):
    """One-time seed of lesson_stats_summary from whatever's already in
    lesson_applications, for anyone upgrading from before this table
    existed. Only runs the (expensive, one-time) aggregation when the
    summary table is empty but lesson_applications has data -- every
    startup after that is a single trivial COUNT check, and every write
    going forward is kept in sync incrementally by
    record_lesson_application()/record_lesson_applications_bulk() instead
    of ever being recomputed from full history again."""
    existing = {r[0] for r in
                conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if "lesson_stats_summary" not in existing or "lesson_applications" not in existing:
        return
    already_seeded = conn.execute("SELECT COUNT(*) FROM lesson_stats_summary").fetchone()[0]
    if already_seeded:
        return
    has_applications = conn.execute("SELECT EXISTS(SELECT 1 FROM lesson_applications LIMIT 1)").fetchone()[0]
    if not has_applications:
        return
    conn.execute(
        """INSERT INTO lesson_stats_summary (lesson_id, times_used, trades_approved, trades_rejected)
           SELECT lesson_id, COUNT(*),
                  SUM(CASE WHEN outcome='approved' THEN 1 ELSE 0 END),
                  SUM(CASE WHEN outcome='rejected' THEN 1 ELSE 0 END)
           FROM lesson_applications GROUP BY lesson_id"""
    )


def _migrate_paper_account_state_per_strategy(conn):
    """paper_account_state used to be a single hardcoded row (id=1) shared by
    every strategy -- wrong now that multiple strategies can each run their
    own independent Paper Trading book (their own balance/PnL/open-position
    cap) at the same time. Converts it to one row per book (strategy_id, or
    the synthetic "__lessons__" key for trades not tied to any specific
    strategy -- see paper_trading.guards.book_key()), recomputed directly
    from paper_positions (the source of truth) rather than trying to split
    the old blended total, since before this change every closed trade fed
    the same shared row regardless of which strategy closed it. Detects the
    old schema via its distinctive "id" column (the new one has no such
    column) so this only ever runs once per database."""
    existing = {r[0] for r in
                conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if "paper_account_state" not in existing:
        return
    columns = {r[1] for r in conn.execute("PRAGMA table_info(paper_account_state)").fetchall()}
    if "strategy_id" in columns:
        return  # already the new per-book schema
    conn.execute("ALTER TABLE paper_account_state RENAME TO paper_account_state_old_global")
    conn.execute(
        """CREATE TABLE paper_account_state (
               strategy_id TEXT PRIMARY KEY,
               realized_pnl_total REAL NOT NULL DEFAULT 0.0,
               closed_count INTEGER NOT NULL DEFAULT 0,
               win_count INTEGER NOT NULL DEFAULT 0,
               updated_at TEXT
           )"""
    )
    if "paper_positions" in existing:
        conn.execute(
            """INSERT INTO paper_account_state (strategy_id, realized_pnl_total, closed_count, win_count, updated_at)
               SELECT COALESCE(strategy_id, '__lessons__'), COALESCE(SUM(pnl), 0.0), COUNT(*),
                      SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END), MAX(closed_at)
               FROM paper_positions
               WHERE status='closed' AND pnl IS NOT NULL
               GROUP BY COALESCE(strategy_id, '__lessons__')"""
        )
    conn.execute("DROP TABLE paper_account_state_old_global")


def _migrate_ai_dictionary_v6_columns(conn):
    """AI Knowledge Learning Engine (v6): Self Building Dictionary entries now
    carry aliases/examples/related concepts/usage notes, not just a bare
    definition -- additive columns only."""
    existing = {r[0] for r in
                conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if "ai_dictionary_entries" not in existing:
        return
    have_columns = {r[1] for r in conn.execute("PRAGMA table_info(ai_dictionary_entries)").fetchall()}
    for col, col_type in _AI_DICTIONARY_V6_COLUMNS.items():
        if col not in have_columns:
            conn.execute(f"ALTER TABLE ai_dictionary_entries ADD COLUMN {col} {col_type}")

_COMPILED_DOCUMENT_NEW_COLUMNS = {
    "ai_assisted": "INTEGER NOT NULL DEFAULT 0",
    "ai_provider": "TEXT",
}


def _migrate_compiled_document_ai_columns(conn):
    """AI Integration Center (Phase 7) tags which compiled documents used an
    AI provider as a pre-processing assist vs. pure rule-based extraction --
    additive columns only, existing rows default to ai_assisted=0."""
    existing = {r[0] for r in
                conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if "compiled_documents" not in existing:
        return
    have_columns = {r[1] for r in conn.execute("PRAGMA table_info(compiled_documents)").fetchall()}
    for col, col_type in _COMPILED_DOCUMENT_NEW_COLUMNS.items():
        if col not in have_columns:
            conn.execute(f"ALTER TABLE compiled_documents ADD COLUMN {col} {col_type}")

_LESSON_META_NEW_COLUMNS = {
    "version": "INTEGER NOT NULL DEFAULT 1",
    "tags_json": "TEXT",
    "supported_market_types_json": "TEXT",
    "supported_timeframes_json": "TEXT",
}


def _migrate_lesson_meta_columns(conn):
    """Phase 5 (Paper Trading) needs a few extra lesson fields (version,
    tags, supported market types/timeframes) that Phase 4 didn't need.
    Additive-only: existing lessons get sensible defaults, nothing rebuilt."""
    existing = {r[0] for r in
                conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if "lessons" not in existing:
        return
    have_columns = {r[1] for r in conn.execute("PRAGMA table_info(lessons)").fetchall()}
    for col, col_type in _LESSON_META_NEW_COLUMNS.items():
        if col not in have_columns:
            conn.execute(f"ALTER TABLE lessons ADD COLUMN {col} {col_type}")

_TRADE_HISTORY_NEW_COLUMNS = {
    "stop_loss": "REAL", "take_profit": "REAL",
    "risk_amount": "REAL", "reward_amount": "REAL", "entry_reason": "TEXT",
    # Trade Execution Engine (Phase 1): which fill mechanism actually
    # produced this trade, and the PnL Engine breakdown (gross PnL,
    # commission, slippage each stored explicitly instead of only the
    # already-netted `pnl`) so every trade is independently auditable
    # without re-deriving costs. is_partial marks a partial-take-profit
    # close -- the remainder of that same position continues as a
    # SEPARATE trade row (same entry_time/entry_price, later exit), so
    # summing pnl across a batch is still correct with no double-counting.
    "entry_type": "TEXT", "gross_pnl": "REAL",
    "commission_cost": "REAL", "slippage_cost": "REAL", "spread_cost": "REAL", "is_partial": "INTEGER",
}


def _migrate_trade_history_columns(conn):
    """2.1 professional update added SL/TP/risk/reward/entry_reason to
    backtest_trades. Additive-only migration: existing rows get NULL for
    the new columns, nothing is rebuilt or lost."""
    existing = {r[0] for r in
                conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if "backtest_trades" not in existing:
        return
    have_columns = {r[1] for r in conn.execute("PRAGMA table_info(backtest_trades)").fetchall()}
    for col, col_type in _TRADE_HISTORY_NEW_COLUMNS.items():
        if col not in have_columns:
            conn.execute(f"ALTER TABLE backtest_trades ADD COLUMN {col} {col_type}")


# NOTE on a fix that was tried and reverted: an earlier version of this
# function wrapped every connection (reads AND writes) in one process-wide
# threading.Lock, on the theory that serializing all access would prevent
# background threads (Paper Trading, Evolution, SINDHU Strategy, the
# automation pipeline) from colliding on SQLite's single-writer rule. That
# made things WORSE, not better: WAL mode already lets any number of
# readers run fully concurrently with each other and with the one writer
# -- there was never a reason to serialize reads -- and forcing everything
# through one lock meant a single thread's own sequential read loop (e.g.
# /api/market's per-coin candle reads for 50 coins, or an Evolution tick's
# per-lineage reads) held the lock for its ENTIRE loop, so every other
# thread's simple queries queued up behind the whole thing. Diagnosed live:
# with the blanket lock in place, /api/market's normal ~57s cold-cache
# warmup (documented below, and already known/expected before this fix)
# started blocking /api/home and other unrelated endpoints for that same
# duration, which they never did before. Reverted.
#
# The real, narrower problem this timeout addresses is writer-vs-writer
# collisions specifically (SQLite's one actual serialization point): if
# two background threads happen to write at the exact same instant, the
# loser waits up to this many seconds for the busy handler before either
# succeeding or raising "database is locked". Lowered from the original 30s
# to 10s -- long enough for another thread's brief write transaction to
# finish, short enough that a genuine collision fails fast instead of
# stalling a request for half a minute. The actual fix for the Evolution
# Engine hangs that motivated this was in evolution_engine/engine.py and
# governor.py: check real CPU/RAM before a tick does ANY work (not only
# inside its mutation loop), and never let a partially-drained queue stay
# stuck -- see EvolutionEngine._tick()'s early resource check and
# Governor.clear_queue().
@contextmanager
def get_conn():
    ensure_folders()
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _table_has_column(conn, table, column):
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def _migrate_add_exchange_column(conn):
    """Older SINDHU databases (pre multi-exchange) have symbols / klines_1m /
    download_progress tables without an `exchange` column, keyed only by
    symbol. Since SQLite can't add a column into a PRIMARY KEY with ALTER
    TABLE, we rename the old table, create the new schema, copy the data
    back in tagging every existing row as 'binance' (the only exchange that
    ever wrote this data), then drop the renamed table. Runs once; a fresh
    or already-migrated database is untouched."""
    existing_tables = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }

    def needs_migration(table):
        return table in existing_tables and not _table_has_column(conn, table, "exchange")

    if not any(needs_migration(t) for t in ("symbols", "klines_1m", "download_progress")):
        return

    if needs_migration("symbols"):
        conn.execute("ALTER TABLE symbols RENAME TO symbols_old")
        conn.execute("""
            CREATE TABLE symbols (
                exchange TEXT NOT NULL,
                symbol TEXT NOT NULL,
                added_at TEXT NOT NULL,
                PRIMARY KEY (exchange, symbol)
            )
        """)
        conn.execute("""
            INSERT INTO symbols (exchange, symbol, added_at)
            SELECT ?, symbol, added_at FROM symbols_old
        """, (DEFAULT_EXCHANGE,))
        conn.execute("DROP TABLE symbols_old")

    if needs_migration("klines_1m"):
        conn.execute("ALTER TABLE klines_1m RENAME TO klines_1m_old")
        conn.execute("""
            CREATE TABLE klines_1m (
                exchange TEXT NOT NULL,
                symbol TEXT NOT NULL,
                open_time INTEGER NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                close_time INTEGER NOT NULL,
                quote_volume REAL NOT NULL,
                trades INTEGER NOT NULL,
                PRIMARY KEY (exchange, symbol, open_time)
            )
        """)
        conn.execute("""
            INSERT INTO klines_1m
                (exchange, symbol, open_time, open, high, low, close, volume, close_time, quote_volume, trades)
            SELECT ?, symbol, open_time, open, high, low, close, volume, close_time, quote_volume, trades
            FROM klines_1m_old
        """, (DEFAULT_EXCHANGE,))
        conn.execute("DROP TABLE klines_1m_old")

    if needs_migration("download_progress"):
        conn.execute("ALTER TABLE download_progress RENAME TO download_progress_old")
        conn.execute("""
            CREATE TABLE download_progress (
                exchange TEXT NOT NULL,
                symbol TEXT NOT NULL,
                last_open_time INTEGER,
                status TEXT NOT NULL DEFAULT 'pending',
                updated_at TEXT,
                PRIMARY KEY (exchange, symbol)
            )
        """)
        conn.execute("""
            INSERT INTO download_progress (exchange, symbol, last_open_time, status, updated_at)
            SELECT ?, symbol, last_open_time, status, updated_at FROM download_progress_old
        """, (DEFAULT_EXCHANGE,))
        conn.execute("DROP TABLE download_progress_old")


def init_db():
    with get_conn() as conn:
        _migrate_add_exchange_column(conn)
        conn.executescript(_SCHEMA)
        _migrate_trade_history_columns(conn)
        _migrate_lesson_meta_columns(conn)
        _migrate_compiled_document_ai_columns(conn)
        _migrate_compiled_document_v6_columns(conn)
        _migrate_ai_dictionary_v6_columns(conn)
        _migrate_ai_import_queue_v6_columns(conn)
        _migrate_ai_import_queue_content_type_column(conn)
        _migrate_ai_import_cache_v8_columns(conn)
        _migrate_backtest_batch_columns(conn)
        _migrate_lesson_stats_summary_backfill(conn)
        _migrate_paper_account_state_per_strategy(conn)
        _migrate_paper_strategy_config_pause_columns(conn)


def save_symbols(exchange, symbols, now_iso):
    with get_conn() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO symbols (exchange, symbol, added_at) VALUES (?, ?, ?)",
            [(exchange, s, now_iso) for s in symbols],
        )
        conn.executemany(
            """INSERT OR IGNORE INTO download_progress (exchange, symbol, last_open_time, status)
               VALUES (?, ?, NULL, 'pending')""",
            [(exchange, s) for s in symbols],
        )


def load_symbols(exchange):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT symbol FROM symbols WHERE exchange = ? ORDER BY symbol", (exchange,)
        ).fetchall()
    return [r[0] for r in rows]


def load_all_exchanges():
    with get_conn() as conn:
        rows = conn.execute("SELECT DISTINCT exchange FROM symbols ORDER BY exchange").fetchall()
    return [r[0] for r in rows]


def get_progress(exchange, symbol):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT last_open_time, status FROM download_progress WHERE exchange = ? AND symbol = ?",
            (exchange, symbol),
        ).fetchone()
    return row if row else (None, "pending")


def set_progress(exchange, symbol, last_open_time, status, now_iso):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO download_progress (exchange, symbol, last_open_time, status, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(exchange, symbol) DO UPDATE SET
                 last_open_time=excluded.last_open_time,
                 status=excluded.status,
                 updated_at=excluded.updated_at""",
            (exchange, symbol, last_open_time, status, now_iso),
        )


def insert_klines(exchange, symbol, rows):
    """rows: iterable of raw OHLCV kline arrays
    (open_time, open, high, low, close, volume, close_time, quote_volume, trades)."""
    if not rows:
        return 0
    with get_conn() as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO klines_1m
               (exchange, symbol, open_time, open, high, low, close, volume, close_time, quote_volume, trades)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    exchange,
                    symbol,
                    r[0],
                    float(r[1]),
                    float(r[2]),
                    float(r[3]),
                    float(r[4]),
                    float(r[5]),
                    r[6],
                    float(r[7]),
                    int(r[8]),
                )
                for r in rows
            ],
        )
    return len(rows)


def count_rows(exchange, symbol):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM klines_1m WHERE exchange = ? AND symbol = ?", (exchange, symbol)
        ).fetchone()
    return row[0]


def count_all_rows():
    """Approximate total candle count for the Home page's display stat only
    -- MAX(_ROWID_) instead of COUNT(*). On this table's ~25M rows COUNT(*)
    took 60-90s (a full index scan; SQLite keeps no cached row count),
    which stalled /api/home (polled by every page). MAX(_ROWID_) reads the
    rightmost b-tree leaf directly (<0.1s) and is off by only rows deleted
    over the table's lifetime (~0.03% here) -- fine for a dashboard number,
    not used anywhere that needs an exact count."""
    with get_conn() as conn:
        row = conn.execute("SELECT MAX(_ROWID_) FROM klines_1m").fetchone()
    return row[0] or 0


def get_klines_range(exchange, symbol, start_ms=None, end_ms=None):
    """Return raw rows ordered by open_time for resampling / backtesting reads."""
    query = (
        "SELECT open_time, open, high, low, close, volume, close_time, quote_volume, trades "
        "FROM klines_1m WHERE exchange = ? AND symbol = ?"
    )
    params = [exchange, symbol]
    if start_ms is not None:
        query += " AND open_time >= ?"
        params.append(start_ms)
    if end_ms is not None:
        query += " AND open_time <= ?"
        params.append(end_ms)
    query += " ORDER BY open_time"
    with get_conn() as conn:
        return conn.execute(query, params).fetchall()


def get_symbol_time_bounds(exchange, symbol):
    """(min_open_time, max_open_time) for a symbol's 1m klines, or (None, None)
    if none stored. Used as a cheap freshness signature for the resample
    cache: SQLite answers MIN/MAX on an indexed column via a direct b-tree
    seek, not a full scan, so this stays fast even on a multi-hundred-
    thousand-row symbol."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT MIN(open_time), MAX(open_time) FROM klines_1m WHERE exchange = ? AND symbol = ?",
            (exchange, symbol),
        ).fetchone()
    return (row[0], row[1]) if row else (None, None)


def db_file_size_bytes():
    try:
        return os.path.getsize(DB_PATH)
    except OSError:
        return 0


# --------------------------------------------------------------- backtesting

def register_strategy(name, file_path, now_iso):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO strategies (name, file_path, added_at) VALUES (?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET file_path=excluded.file_path""",
            (name, file_path, now_iso),
        )


def create_batch(batch_id, strategy_name, exchange, settings, now_iso):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO backtest_batches (batch_id, strategy_name, exchange, settings_json, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'running', ?, ?)""",
            (batch_id, strategy_name, exchange, json.dumps(settings), now_iso, now_iso),
        )


def get_batch(batch_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT batch_id, strategy_name, exchange, settings_json, status, created_at, updated_at, display_name "
            "FROM backtest_batches WHERE batch_id = ?",
            (batch_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "batch_id": row[0], "strategy_name": row[1], "exchange": row[2],
        "settings": json.loads(row[3]), "status": row[4],
        "created_at": row[5], "updated_at": row[6], "display_name": row[7],
    }


def list_recent_batches(limit=30):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT batch_id, strategy_name, exchange, settings_json, status, created_at, updated_at, display_name "
            "FROM backtest_batches ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {"batch_id": r[0], "strategy_name": r[1], "exchange": r[2],
         "settings": json.loads(r[3]), "status": r[4], "created_at": r[5], "updated_at": r[6],
         "display_name": r[7]}
        for r in rows
    ]


def update_batch_status(batch_id, status, now_iso):
    with get_conn() as conn:
        conn.execute(
            "UPDATE backtest_batches SET status = ?, updated_at = ? WHERE batch_id = ?",
            (status, now_iso, batch_id),
        )


def set_batch_display_name(batch_id, display_name):
    """Purely a display label (Part 3) -- never touches strategy_name,
    settings_json, or any result/trade row, so renaming can never affect
    what the batch actually contains or how it's re-derived."""
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE backtest_batches SET display_name = ? WHERE batch_id = ?",
            (display_name, batch_id),
        )
        return cur.rowcount > 0


def save_optimization(opt_id, strategy_id, original_batch_id, optimized_batch_id,
                       winner, params_changed, candidates_tried, now_iso):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO strategy_optimizations
               (id, strategy_id, original_batch_id, optimized_batch_id, winner,
                params_changed_json, candidates_tried_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (opt_id, strategy_id, original_batch_id, optimized_batch_id, winner,
             json.dumps(params_changed), json.dumps(candidates_tried), now_iso),
        )


def get_optimization_for_batch(batch_id):
    """The optimization record (if any) where this batch_id is either the
    original or the optimized side -- used by the Backtest History
    comparison view to know which other batch to show alongside this one."""
    with get_conn() as conn:
        row = conn.execute(
            """SELECT id, strategy_id, original_batch_id, optimized_batch_id, winner,
                      params_changed_json, candidates_tried_json, created_at
               FROM strategy_optimizations
               WHERE original_batch_id = ? OR optimized_batch_id = ?
               ORDER BY created_at DESC LIMIT 1""",
            (batch_id, batch_id),
        ).fetchone()
    if not row:
        return None
    return {
        "id": row[0], "strategy_id": row[1], "original_batch_id": row[2],
        "optimized_batch_id": row[3], "winner": row[4],
        "params_changed": json.loads(row[5]) if row[5] else [],
        "candidates_tried": json.loads(row[6]) if row[6] else [],
        "created_at": row[7],
    }


def list_optimizations(limit=200):
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT id, strategy_id, original_batch_id, optimized_batch_id, winner,
                      params_changed_json, candidates_tried_json, created_at
               FROM strategy_optimizations ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [
        {"id": r[0], "strategy_id": r[1], "original_batch_id": r[2],
         "optimized_batch_id": r[3], "winner": r[4],
         "params_changed": json.loads(r[5]) if r[5] else [],
         "candidates_tried": json.loads(r[6]) if r[6] else [],
         "created_at": r[7]}
        for r in rows
    ]


def create_pipeline_job(job_id, strategy_id, strategy_name, symbols, now_iso):
    """First row for a new Automation Pipeline run -- status='running' from
    the moment it's created. If the server dies before this row is even
    written, there's nothing to resume (equivalent to the trigger never
    having happened), which is the correct, safe outcome."""
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO pipeline_jobs
               (job_id, strategy_id, strategy_name, symbols_json, status, stage, checkpoint_json, error, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'running', 'sanity_check', '{}', NULL, ?, ?)""",
            (job_id, strategy_id, strategy_name, json.dumps(symbols) if symbols else None, now_iso, now_iso),
        )


def update_pipeline_job(job_id, now_iso, stage=None, checkpoint=None, status=None, error=None):
    """Updates whichever fields are given; None means "leave unchanged".
    `checkpoint`, when given, REPLACES the stored checkpoint_json wholesale
    (the caller in automation_pipeline/pipeline.py keeps the full checkpoint
    dict in memory and always passes the complete, current version -- so
    there's never a partial-merge to get wrong here). `now_iso` is required,
    same convention as every other storage write in this module."""
    fields, values = ["updated_at = ?"], [now_iso]
    if stage is not None:
        fields.append("stage = ?")
        values.append(stage)
    if checkpoint is not None:
        fields.append("checkpoint_json = ?")
        values.append(json.dumps(checkpoint))
    if status is not None:
        fields.append("status = ?")
        values.append(status)
    if error is not None:
        fields.append("error = ?")
        values.append(error)
    values.append(job_id)
    with get_conn() as conn:
        conn.execute(f"UPDATE pipeline_jobs SET {', '.join(fields)} WHERE job_id = ?", values)


def get_pipeline_job(job_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT job_id, strategy_id, strategy_name, symbols_json, status, stage, checkpoint_json, error, created_at, updated_at "
            "FROM pipeline_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "job_id": row[0], "strategy_id": row[1], "strategy_name": row[2],
        "symbols": json.loads(row[3]) if row[3] else None,
        "status": row[4], "stage": row[5],
        "checkpoint": json.loads(row[6]) if row[6] else {},
        "error": row[7], "created_at": row[8], "updated_at": row[9],
    }


def list_running_pipeline_jobs():
    """Every pipeline_jobs row still marked 'running' -- checked once at
    server startup. A row can only be in this state if the server stopped
    (crash, power loss, or a forceful kill) before the pipeline reached one
    of its own terminal states (completed/stopped/failed), since every
    normal exit path -- success, a user Stop, or a caught error -- updates
    status before returning. This is exactly the resume/fail decision
    point."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT job_id, strategy_id, strategy_name, symbols_json, status, stage, checkpoint_json, error, created_at, updated_at "
            "FROM pipeline_jobs WHERE status = 'running'"
        ).fetchall()
    return [
        {
            "job_id": r[0], "strategy_id": r[1], "strategy_name": r[2],
            "symbols": json.loads(r[3]) if r[3] else None,
            "status": r[4], "stage": r[5],
            "checkpoint": json.loads(r[6]) if r[6] else {},
            "error": r[7], "created_at": r[8], "updated_at": r[9],
        }
        for r in rows
    ]


def list_pipeline_jobs(limit=200, status=None):
    """Every automation pipeline run ever started, permanently listed
    (unlike list_running_pipeline_jobs, which only ever returns the
    currently-interrupted ones checked at startup) -- newest first. This is
    the backing data for the Automation Pipeline History page: the same
    pipeline_jobs rows already written by trigger_pipeline_for_strategy()/
    run_pipeline()'s checkpointing, not a separate tracking system."""
    query = ("SELECT job_id, strategy_id, strategy_name, symbols_json, status, stage, "
             "checkpoint_json, error, created_at, updated_at FROM pipeline_jobs")
    params = []
    if status:
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [
        {
            "job_id": r[0], "strategy_id": r[1], "strategy_name": r[2],
            "symbols": json.loads(r[3]) if r[3] else None,
            "status": r[4], "stage": r[5],
            "checkpoint": json.loads(r[6]) if r[6] else {},
            "error": r[7], "created_at": r[8], "updated_at": r[9],
        }
        for r in rows
    ]


def get_completed_result_keys(batch_id):
    """{(symbol, timeframe)} already completed for this batch -- used to skip
    finished work when a batch resumes."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT symbol, timeframe FROM backtest_results WHERE batch_id = ? AND status = 'completed'",
            (batch_id,),
        ).fetchall()
    return {(r[0], r[1]) for r in rows}


def save_result(batch_id, symbol, timeframe, status, metrics, now_iso):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO backtest_results (batch_id, symbol, timeframe, status, metrics_json, completed_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(batch_id, symbol, timeframe) DO UPDATE SET
                 status=excluded.status, metrics_json=excluded.metrics_json, completed_at=excluded.completed_at""",
            (batch_id, symbol, timeframe, status, json.dumps(metrics) if metrics is not None else None, now_iso),
        )


def save_trades(batch_id, symbol, timeframe, trades):
    if not trades:
        return
    with get_conn() as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO backtest_trades
               (batch_id, symbol, timeframe, trade_num, side, entry_time, entry_price,
                exit_time, exit_price, size, pnl, pnl_pct, exit_reason,
                stop_loss, take_profit, risk_amount, reward_amount, entry_reason,
                entry_type, gross_pnl, commission_cost, slippage_cost, spread_cost, is_partial)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    batch_id, symbol, timeframe, t["trade_num"], t["side"],
                    t["entry_time"], t["entry_price"], t.get("exit_time"), t.get("exit_price"),
                    t["size"], t.get("pnl"), t.get("pnl_pct"), t.get("exit_reason"),
                    t.get("stop_loss"), t.get("take_profit"), t.get("risk_amount"),
                    t.get("reward_amount"), t.get("entry_reason"),
                    t.get("entry_type"), t.get("gross_pnl"), t.get("commission_cost"),
                    t.get("slippage_cost"), t.get("spread_cost"), 1 if t.get("is_partial") else 0,
                )
                for t in trades
            ],
        )


def get_trades(batch_id, symbol=None, timeframe=None):
    query = (
        "SELECT batch_id, symbol, timeframe, trade_num, side, entry_time, entry_price, "
        "exit_time, exit_price, size, pnl, pnl_pct, exit_reason, "
        "stop_loss, take_profit, risk_amount, reward_amount, entry_reason, "
        "entry_type, gross_pnl, commission_cost, slippage_cost, spread_cost, is_partial "
        "FROM backtest_trades WHERE batch_id = ?"
    )
    params = [batch_id]
    if symbol is not None:
        query += " AND symbol = ?"
        params.append(symbol)
    if timeframe is not None:
        query += " AND timeframe = ?"
        params.append(timeframe)
    query += " ORDER BY symbol, timeframe, trade_num"

    cols = ["batch_id", "symbol", "timeframe", "trade_num", "side", "entry_time", "entry_price",
            "exit_time", "exit_price", "size", "pnl", "pnl_pct", "exit_reason",
            "stop_loss", "take_profit", "risk_amount", "reward_amount", "entry_reason",
            "entry_type", "gross_pnl", "commission_cost", "slippage_cost", "spread_cost", "is_partial"]
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(zip(cols, r)) for r in rows]


def search_trades(query, limit=10):
    """Global trade search (across every batch) by symbol substring, most
    recent first -- backs the dashboard's Global Search box."""
    like = f"%{query}%"
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT batch_id, symbol, timeframe, trade_num, side, pnl, pnl_pct, entry_time
               FROM backtest_trades WHERE symbol LIKE ? ORDER BY entry_time DESC LIMIT ?""",
            (like, limit),
        ).fetchall()
    return [
        {"batch_id": r[0], "symbol": r[1], "timeframe": r[2], "trade_num": r[3],
         "side": r[4], "pnl": r[5], "pnl_pct": r[6], "entry_time": r[7]}
        for r in rows
    ]


def get_batch_results(batch_id):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT symbol, timeframe, status, metrics_json, completed_at FROM backtest_results WHERE batch_id = ?",
            (batch_id,),
        ).fetchall()
    return [
        {"symbol": r[0], "timeframe": r[1], "status": r[2],
         "metrics": json.loads(r[3]) if r[3] else None, "completed_at": r[4]}
        for r in rows
    ]


# --------------------------------------------------------------- lessons (Knowledge Engine)

_LESSON_COLUMNS = [
    "id", "title", "category", "description", "priority", "status", "notes",
    "apply_backtesting", "apply_paper_trading", "apply_evolution",
    "rule_type", "direction", "conditions_json", "created_at", "updated_at",
    "version", "tags_json", "supported_market_types_json", "supported_timeframes_json",
]


def _row_to_lesson_dict(row):
    d = dict(zip(_LESSON_COLUMNS, row))
    d["apply_backtesting"] = bool(d["apply_backtesting"])
    d["apply_paper_trading"] = bool(d["apply_paper_trading"])
    d["apply_evolution"] = bool(d["apply_evolution"])
    d["conditions"] = json.loads(d.pop("conditions_json")) if d.get("conditions_json") else []
    d["tags"] = json.loads(d.pop("tags_json")) if d.get("tags_json") else []
    d["supported_market_types"] = json.loads(d.pop("supported_market_types_json")) if d.get("supported_market_types_json") else []
    d["supported_timeframes"] = json.loads(d.pop("supported_timeframes_json")) if d.get("supported_timeframes_json") else []
    return d


def save_lesson(lesson):
    """lesson: dict with the fields in _LESSON_COLUMNS (a "conditions" list
    instead of conditions_json -- serialized here). Insert or update by id."""
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO lessons (id, title, category, description, priority, status, notes,
                apply_backtesting, apply_paper_trading, apply_evolution, rule_type, direction,
                conditions_json, created_at, updated_at, version, tags_json,
                supported_market_types_json, supported_timeframes_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 title=excluded.title, category=excluded.category, description=excluded.description,
                 priority=excluded.priority, status=excluded.status, notes=excluded.notes,
                 apply_backtesting=excluded.apply_backtesting, apply_paper_trading=excluded.apply_paper_trading,
                 apply_evolution=excluded.apply_evolution, rule_type=excluded.rule_type,
                 direction=excluded.direction, conditions_json=excluded.conditions_json,
                 updated_at=excluded.updated_at, version=excluded.version, tags_json=excluded.tags_json,
                 supported_market_types_json=excluded.supported_market_types_json,
                 supported_timeframes_json=excluded.supported_timeframes_json""",
            (
                lesson["id"], lesson["title"], lesson["category"], lesson.get("description"),
                lesson.get("priority", "Medium"), lesson.get("status", "active"), lesson.get("notes"),
                int(lesson.get("apply_backtesting", True)), int(lesson.get("apply_paper_trading", True)),
                int(lesson.get("apply_evolution", True)), lesson.get("rule_type", "block_if_true"),
                lesson.get("direction"), json.dumps(lesson.get("conditions", [])),
                lesson["created_at"], lesson["updated_at"], lesson.get("version", 1),
                json.dumps(lesson.get("tags", [])), json.dumps(lesson.get("supported_market_types", [])),
                json.dumps(lesson.get("supported_timeframes", [])),
            ),
        )


def get_lesson(lesson_id):
    with get_conn() as conn:
        row = conn.execute(
            f"SELECT {','.join(_LESSON_COLUMNS)} FROM lessons WHERE id = ?", (lesson_id,)
        ).fetchone()
    return _row_to_lesson_dict(row) if row else None


def list_lessons(status=None, category=None, apply_backtesting=None):
    query = f"SELECT {','.join(_LESSON_COLUMNS)} FROM lessons"
    clauses, params = [], []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if category:
        clauses.append("category = ?")
        params.append(category)
    if apply_backtesting is not None:
        clauses.append("apply_backtesting = ?")
        params.append(int(apply_backtesting))
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY created_at DESC"
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_lesson_dict(r) for r in rows]


def delete_lesson(lesson_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))
        conn.execute("DELETE FROM lesson_applications WHERE lesson_id = ?", (lesson_id,))
        conn.execute("DELETE FROM lesson_stats_summary WHERE lesson_id = ?", (lesson_id,))


def _bump_lesson_stats_summary(conn, lesson_id, outcome):
    """Incrementally keeps lesson_stats_summary in sync with every row
    written to lesson_applications -- an UPSERT that adds 1 to times_used
    (always) and to trades_approved/trades_rejected (only for a matching
    outcome), so get_lesson_stats()/get_lesson_stats_bulk() never need to
    re-aggregate lesson_applications' full history again."""
    conn.execute(
        """INSERT INTO lesson_stats_summary (lesson_id, times_used, trades_approved, trades_rejected)
           VALUES (?, 1, ?, ?)
           ON CONFLICT(lesson_id) DO UPDATE SET
             times_used = times_used + 1,
             trades_approved = trades_approved + excluded.trades_approved,
             trades_rejected = trades_rejected + excluded.trades_rejected""",
        (lesson_id, 1 if outcome == "approved" else 0, 1 if outcome == "rejected" else 0),
    )


def record_lesson_application(lesson_id, batch_id, symbol, timeframe, outcome, now_iso):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO lesson_applications (lesson_id, batch_id, symbol, timeframe, applied_at, outcome)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (lesson_id, batch_id, symbol, timeframe, now_iso, outcome),
        )
        _bump_lesson_stats_summary(conn, lesson_id, outcome)


def record_lesson_applications_bulk(rows):
    """Same as record_lesson_application but for many rows in one
    connection/commit -- rows is an iterable of
    (lesson_id, batch_id, symbol, timeframe, applied_at, outcome) tuples
    (same column order as the table). Used by KnowledgeEngine to flush a
    whole backtest run's worth of per-bar lesson checks in a single write
    instead of one connection per bar. Aggregates per lesson_id in Python
    first so the summary UPSERT is one statement per distinct lesson in
    this batch, not one per row."""
    rows = list(rows)
    if not rows:
        return
    deltas = {}
    for lesson_id, _batch_id, _symbol, _timeframe, _applied_at, outcome in rows:
        d = deltas.setdefault(lesson_id, {"times_used": 0, "trades_approved": 0, "trades_rejected": 0})
        d["times_used"] += 1
        if outcome == "approved":
            d["trades_approved"] += 1
        elif outcome == "rejected":
            d["trades_rejected"] += 1
    with get_conn() as conn:
        conn.executemany(
            """INSERT INTO lesson_applications (lesson_id, batch_id, symbol, timeframe, applied_at, outcome)
               VALUES (?, ?, ?, ?, ?, ?)""",
            rows,
        )
        conn.executemany(
            """INSERT INTO lesson_stats_summary (lesson_id, times_used, trades_approved, trades_rejected)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(lesson_id) DO UPDATE SET
                 times_used = times_used + excluded.times_used,
                 trades_approved = trades_approved + excluded.trades_approved,
                 trades_rejected = trades_rejected + excluded.trades_rejected""",
            [(lesson_id, d["times_used"], d["trades_approved"], d["trades_rejected"]) for lesson_id, d in deltas.items()],
        )


_EMPTY_LESSON_STATS = {"times_used": 0, "trades_approved": 0, "trades_rejected": 0}


def get_lesson_stats(lesson_id):
    """Reads the incrementally-maintained summary (O(1) primary-key lookup)
    instead of aggregating lesson_applications' full history on every call
    -- see lesson_stats_summary's schema comment and _bump_lesson_stats_summary()."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT times_used, trades_approved, trades_rejected FROM lesson_stats_summary WHERE lesson_id = ?",
            (lesson_id,),
        ).fetchone()
    if not row:
        return dict(_EMPTY_LESSON_STATS)
    times_used, approved, rejected = row
    return {"times_used": times_used, "trades_approved": approved, "trades_rejected": rejected}


def get_lesson_stats_bulk(lesson_ids):
    """Same shape as get_lesson_stats(), but for many lessons in one query
    instead of one query per lesson -- what the Knowledge page's lesson
    list actually needs. Reads lesson_stats_summary directly (no
    aggregation at read time at all -- see that table's schema comment).
    Lesson ids with no applications yet simply aren't in
    lesson_stats_summary -- callers get all-zero stats for those via the
    .get(..., default) at the call site."""
    lesson_ids = list(lesson_ids)
    if not lesson_ids:
        return {}
    placeholders = ",".join("?" for _ in lesson_ids)
    with get_conn() as conn:
        rows = conn.execute(
            f"""SELECT lesson_id, times_used, trades_approved, trades_rejected
                FROM lesson_stats_summary WHERE lesson_id IN ({placeholders})""",
            lesson_ids,
        ).fetchall()
    return {
        lesson_id: {"times_used": times_used, "trades_approved": approved, "trades_rejected": rejected}
        for lesson_id, times_used, approved, rejected in rows
    }


def get_batch_lesson_stats(batch_id):
    with get_conn() as conn:
        row = conn.execute(
            """SELECT
                 SUM(CASE WHEN outcome='approved' THEN 1 ELSE 0 END),
                 SUM(CASE WHEN outcome='rejected' THEN 1 ELSE 0 END),
                 COUNT(DISTINCT lesson_id)
               FROM lesson_applications WHERE batch_id = ?""",
            (batch_id,),
        ).fetchone()
    approved, rejected, lessons_used = row
    return {
        "trades_approved_by_lessons": approved or 0,
        "trades_rejected_by_lessons": rejected or 0,
        "lessons_applied": lessons_used or 0,
    }


def log_activity(entity, action, message, now_iso):
    """Append-only feed backing the dashboard's live Activity Feed. Capped
    at the most recent 500 rows so it never grows unbounded."""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO activity_log (entity, action, message, created_at) VALUES (?, ?, ?, ?)",
            (entity, action, message, now_iso),
        )
        conn.execute(
            """DELETE FROM activity_log WHERE id NOT IN (
                 SELECT id FROM activity_log ORDER BY id DESC LIMIT 500
               )"""
        )


def list_activity(limit=50):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, entity, action, message, created_at FROM activity_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {"id": r[0], "entity": r[1], "action": r[2], "message": r[3], "created_at": r[4]}
        for r in rows
    ]


def get_knowledge_report():
    # Reads the running totals in lesson_stats_summary (one row per lesson,
    # kept in sync incrementally at write time) rather than aggregating
    # lesson_applications directly. That table has grown to 25 MILLION rows
    # (one per lesson per bar checked during backtests), and even a single
    # conditional-aggregation pass over it measured 40+ SECONDS -- with this
    # endpoint feeding /api/home, which every page's topbar polls, that one
    # slow query stalled the entire app every time the 60s cache expired.
    # Summing the tiny summary table instead measures 0.47ms (~86,000x
    # faster) and was verified to return byte-identical totals.
    with get_conn() as conn:
        lessons_row = conn.execute(
            "SELECT COUNT(*), "
            "SUM(CASE WHEN status='active' THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN status='disabled' THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN status='draft' THEN 1 ELSE 0 END) "
            "FROM lessons"
        ).fetchone()
        total, active, disabled, draft = (v or 0 for v in lessons_row)
        applications_row = conn.execute(
            "SELECT COALESCE(SUM(times_used), 0), "
            "COALESCE(SUM(trades_rejected), 0), "
            "COALESCE(SUM(trades_approved), 0) "
            "FROM lesson_stats_summary"
        ).fetchone()
        applied, rejected, approved = (v or 0 for v in applications_row)
        by_category = conn.execute("SELECT category, COUNT(*) FROM lessons GROUP BY category").fetchall()
    return {
        "total_lessons": total, "active_lessons": active, "disabled_lessons": disabled,
        "draft_lessons": draft, "lessons_applied": applied,
        "trades_rejected_by_lessons": rejected, "trades_approved_by_lessons": approved,
        "categories": {c: n for c, n in by_category},
    }


# --------------------------------------------------------------- paper trading

_PAPER_POSITION_COLUMNS = [
    "id", "exchange", "symbol", "direction", "entry_price", "exit_price", "stop_loss",
    "take_profit", "size", "risk_amount", "entry_time", "exit_time", "pnl", "pnl_pct",
    "exit_reason", "entry_reason", "strategy_id", "strategy_name", "strategy_version",
    "lesson_ids_json", "confidence", "market_snapshot_json", "tags_json", "session",
    "timeframe", "market_state", "lifecycle_json", "reflection_json", "status",
    "created_at", "closed_at",
]


def _row_to_paper_position(row):
    d = dict(zip(_PAPER_POSITION_COLUMNS, row))
    d["lesson_ids"] = json.loads(d.pop("lesson_ids_json")) if d.get("lesson_ids_json") else []
    d["market_snapshot"] = json.loads(d.pop("market_snapshot_json")) if d.get("market_snapshot_json") else {}
    d["tags"] = json.loads(d.pop("tags_json")) if d.get("tags_json") else []
    d["lifecycle"] = json.loads(d.pop("lifecycle_json")) if d.get("lifecycle_json") else {}
    d["reflection"] = json.loads(d.pop("reflection_json")) if d.get("reflection_json") else None
    # Derived, not stored separately -- is_win/rr (the R-multiple actually
    # achieved: realized pnl divided by the amount originally risked) are
    # always recomputable from pnl/risk_amount, so keeping them out of the
    # schema avoids a second source of truth that could drift.
    if d["status"] == "closed" and d.get("pnl") is not None:
        d["is_win"] = d["pnl"] > 0
        d["rr"] = (d["pnl"] / d["risk_amount"]) if d.get("risk_amount") else None
    else:
        d["is_win"] = None
        d["rr"] = None
    return d


def open_paper_position(pos):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO paper_positions
               (id, exchange, symbol, direction, entry_price, stop_loss, take_profit, size,
                risk_amount, entry_time, entry_reason, strategy_id, strategy_name, strategy_version,
                lesson_ids_json, confidence, market_snapshot_json, tags_json, session, timeframe,
                market_state, lifecycle_json, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)""",
            (
                pos["id"], pos["exchange"], pos["symbol"], pos["direction"], pos["entry_price"],
                pos.get("stop_loss"), pos.get("take_profit"), pos["size"], pos.get("risk_amount"),
                pos["entry_time"], pos.get("entry_reason"), pos.get("strategy_id"), pos.get("strategy_name"),
                pos.get("strategy_version"), json.dumps(pos.get("lesson_ids", [])), pos.get("confidence"),
                json.dumps(pos.get("market_snapshot", {})), json.dumps(pos.get("tags", [])),
                pos.get("session"), pos.get("timeframe"), pos.get("market_state"),
                json.dumps(pos.get("lifecycle", {})), pos["created_at"],
            ),
        )


def _account_state_key(book_key):
    """paper_positions.strategy_id is NULL for trades not tied to any
    specific strategy (lesson-only signals) -- paper_account_state has no
    NULL primary key, so those share the synthetic "__lessons__" row
    instead. See paper_trading.guards.book_key()."""
    return book_key or "__lessons__"


def close_paper_position(position_id, exit_price, exit_time, pnl, pnl_pct, exit_reason,
                          lifecycle, reflection, closed_at, book_key=None):
    with get_conn() as conn:
        conn.execute(
            """UPDATE paper_positions SET
                 exit_price=?, exit_time=?, pnl=?, pnl_pct=?, exit_reason=?,
                 lifecycle_json=?, reflection_json=?, status='closed', closed_at=?
               WHERE id=?""",
            (exit_price, exit_time, pnl, pnl_pct, exit_reason,
             json.dumps(lifecycle), json.dumps(reflection), closed_at, position_id),
        )
        if pnl is not None:
            conn.execute(
                """INSERT INTO paper_account_state (strategy_id, realized_pnl_total, closed_count, win_count, updated_at)
                   VALUES (?, ?, 1, ?, ?)
                   ON CONFLICT(strategy_id) DO UPDATE SET
                     realized_pnl_total = realized_pnl_total + excluded.realized_pnl_total,
                     closed_count = closed_count + 1,
                     win_count = win_count + excluded.win_count,
                     updated_at = excluded.updated_at""",
                (_account_state_key(book_key), pnl, 1 if pnl > 0 else 0, closed_at),
            )


def get_paper_realized_pnl_total(book_key):
    """O(1) running total for one book (a strategy_id, or "__lessons__"),
    kept in sync by close_paper_position() -- see
    _migrate_paper_account_state_per_strategy() for why this replaced a live
    SUM() scan over every closed position on every call."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT realized_pnl_total FROM paper_account_state WHERE strategy_id=?",
            (_account_state_key(book_key),),
        ).fetchone()
    return row[0] if row else 0.0


def get_paper_account_summary(book_key):
    """{realized_pnl_total, closed_count, win_count} for one book, O(1) via
    the running total kept in sync by close_paper_position()."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT realized_pnl_total, closed_count, win_count FROM paper_account_state WHERE strategy_id=?",
            (_account_state_key(book_key),),
        ).fetchone()
    if not row:
        return {"realized_pnl_total": 0.0, "closed_count": 0, "win_count": 0}
    return {"realized_pnl_total": row[0], "closed_count": row[1], "win_count": row[2]}


def list_paper_account_states():
    """Every book's running total -- used for the Home page's combined
    snapshot and the Paper Trading analytics dashboard's per-strategy view."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT strategy_id, realized_pnl_total, closed_count, win_count, updated_at FROM paper_account_state"
        ).fetchall()
    cols = ["strategy_id", "realized_pnl_total", "closed_count", "win_count", "updated_at"]
    return [dict(zip(cols, r)) for r in rows]


def get_open_paper_positions(exchange=None, symbol=None, direction=None, strategy_id=None):
    query = f"SELECT {','.join(_PAPER_POSITION_COLUMNS)} FROM paper_positions WHERE status='open'"
    params = []
    if exchange:
        query += " AND exchange = ?"
        params.append(exchange)
    if symbol:
        query += " AND symbol = ?"
        params.append(symbol)
    if direction:
        query += " AND direction = ?"
        params.append(direction)
    if strategy_id is not None:
        if strategy_id == "__lessons__":
            query += " AND strategy_id IS NULL"
        else:
            query += " AND strategy_id = ?"
            params.append(strategy_id)
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_paper_position(r) for r in rows]


def get_open_paper_position_symbols(strategy_id):
    """Distinct coins this one book currently has an open position on --
    used for the per-strategy "max coins actively traded" cap."""
    query = "SELECT DISTINCT symbol FROM paper_positions WHERE status='open'"
    params = []
    if strategy_id == "__lessons__":
        query += " AND strategy_id IS NULL"
    else:
        query += " AND strategy_id = ?"
        params.append(strategy_id)
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return {r[0] for r in rows}


def get_paper_position(position_id):
    with get_conn() as conn:
        row = conn.execute(
            f"SELECT {','.join(_PAPER_POSITION_COLUMNS)} FROM paper_positions WHERE id=?", (position_id,)
        ).fetchone()
    return _row_to_paper_position(row) if row else None


def list_closed_paper_positions(limit=100, strategy_id=None, since_iso=None):
    query = f"SELECT {','.join(_PAPER_POSITION_COLUMNS)} FROM paper_positions WHERE status='closed'"
    params = []
    if strategy_id is not None:
        if strategy_id == "__lessons__":
            query += " AND strategy_id IS NULL"
        else:
            query += " AND strategy_id = ?"
            params.append(strategy_id)
    if since_iso:
        query += " AND closed_at >= ?"
        params.append(since_iso)
    query += " ORDER BY closed_at DESC LIMIT ?"
    params.append(limit)
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_paper_position(r) for r in rows]


def last_closed_paper_position(exchange, symbol, direction=None, strategy_id=None):
    """Most recently closed position for this coin (scoped to one book) --
    used for Cooldown, so one strategy's cooldown never blocks another
    strategy's independent trade on the same coin."""
    query = ("SELECT " + ",".join(_PAPER_POSITION_COLUMNS) + " FROM paper_positions "
             "WHERE status='closed' AND exchange=? AND symbol=?")
    params = [exchange, symbol]
    if direction:
        query += " AND direction=?"
        params.append(direction)
    if strategy_id is not None:
        if strategy_id == "__lessons__":
            query += " AND strategy_id IS NULL"
        else:
            query += " AND strategy_id = ?"
            params.append(strategy_id)
    query += " ORDER BY closed_at DESC LIMIT 1"
    with get_conn() as conn:
        row = conn.execute(query, params).fetchone()
    return _row_to_paper_position(row) if row else None


def get_paper_period_summary(since_iso=None, until_iso=None):
    """Aggregate stats over CLOSED trades only in [since_iso, until_iso) --
    both bounds optional (None on both = All-Time). Open positions never
    factor in here (see get_open_paper_positions for that separate count),
    so this number always reflects only completed outcomes.

    "avg_rr" is the MEDIAN R-multiple achieved (realized pnl divided by the
    amount originally risked) -- a plain mean was tried first and rejected:
    a handful of trades with a razor-thin planned risk (a stop just pennies
    from entry) produce R-multiples in the hundreds, which drag a simple
    average to a number no longer representative of a typical trade (in
    real data: mean ~9.9 vs median ~1.9 over the same 624 trades). The mean
    is still returned separately as avg_rr_mean for anyone who wants it."""
    query = ("SELECT COUNT(*), COALESCE(SUM(pnl),0), SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END), "
             "COUNT(DISTINCT strategy_id) FROM paper_positions WHERE status='closed' AND pnl IS NOT NULL")
    params = []
    if since_iso:
        query += " AND closed_at >= ?"
        params.append(since_iso)
    if until_iso:
        query += " AND closed_at < ?"
        params.append(until_iso)
    rr_query = "SELECT pnl, risk_amount FROM paper_positions WHERE status='closed' AND pnl IS NOT NULL AND risk_amount > 0"
    rr_params = []
    if since_iso:
        rr_query += " AND closed_at >= ?"
        rr_params.append(since_iso)
    if until_iso:
        rr_query += " AND closed_at < ?"
        rr_params.append(until_iso)
    with get_conn() as conn:
        row = conn.execute(query, params).fetchone()
        rr_rows = conn.execute(rr_query, rr_params).fetchall()
    total, pnl, wins, strategies = row
    total = total or 0
    rr_values = [p / r for p, r in rr_rows]
    avg_rr_median = round(statistics.median(rr_values), 3) if rr_values else None
    avg_rr_mean = round(statistics.mean(rr_values), 3) if rr_values else None
    return {
        "closed_trades": total,
        "total_pnl": pnl or 0.0,
        "win_count": wins or 0,
        "win_rate": round(wins / total * 100, 2) if total else 0.0,
        "active_strategies": strategies or 0,
        "avg_rr": avg_rr_median,
        "avg_rr_mean": avg_rr_mean,
    }


def list_paper_coin_stats(since_iso=None, until_iso=None):
    """Every coin that has ever closed a trade, ranked by total pnl --
    best-performing coin is the first entry, worst is the last, independent
    of which strategy traded it."""
    query = ("SELECT symbol, COUNT(*), COALESCE(SUM(pnl),0), SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END) "
             "FROM paper_positions WHERE status='closed' AND pnl IS NOT NULL")
    params = []
    if since_iso:
        query += " AND closed_at >= ?"
        params.append(since_iso)
    if until_iso:
        query += " AND closed_at < ?"
        params.append(until_iso)
    query += " GROUP BY symbol ORDER BY SUM(pnl) DESC"
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [
        {"symbol": r[0], "closed_trades": r[1], "total_pnl": r[2],
         "win_rate": round(r[3] / r[1] * 100, 2) if r[1] else 0.0}
        for r in rows
    ]


def list_paper_strategy_stats(since_iso=None, until_iso=None):
    """Every strategy that has ever closed a trade (a permanent record --
    a strategy later disabled or deleted from the library still keeps its
    history here), ranked by total pnl. "trading_since" is the earliest
    position (open or closed) ever recorded for that strategy, computed
    across all history regardless of since_iso/until_iso so it always
    answers "since when has this strategy been running" rather than
    "since when in this period.\""""
    query = ("SELECT strategy_id, MAX(strategy_name), COUNT(*), COALESCE(SUM(pnl),0), "
             "SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END) FROM paper_positions "
             "WHERE status='closed' AND pnl IS NOT NULL AND strategy_id IS NOT NULL")
    params = []
    if since_iso:
        query += " AND closed_at >= ?"
        params.append(since_iso)
    if until_iso:
        query += " AND closed_at < ?"
        params.append(until_iso)
    query += " GROUP BY strategy_id"
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
        since_rows = conn.execute(
            "SELECT strategy_id, MIN(created_at) FROM paper_positions "
            "WHERE strategy_id IS NOT NULL GROUP BY strategy_id"
        ).fetchall()
    since_map = dict(since_rows)
    result = [
        {
            "strategy_id": sid, "strategy_name": name, "closed_trades": count,
            "total_pnl": pnl, "win_count": wins,
            "win_rate": round(wins / count * 100, 2) if count else 0.0,
            "trading_since": since_map.get(sid),
        }
        for sid, name, count, pnl, wins in rows
    ]
    result.sort(key=lambda r: r["total_pnl"], reverse=True)
    return result


def list_paper_strategy_trading_since():
    """{strategy_id: earliest created_at} across ALL positions (open or
    closed) -- used to show "trading since" for a strategy that has open
    positions but hasn't closed any trade yet."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT strategy_id, MIN(created_at) FROM paper_positions "
            "WHERE strategy_id IS NOT NULL GROUP BY strategy_id"
        ).fetchall()
    return dict(rows)


def log_paper_decision(entry):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO paper_decision_log
               (exchange, symbol, direction, decision, reason, strategy_id, strategy_name,
                lesson_ids_json, confidence, market_state, session, timeframe, position_id,
                market_snapshot_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry["exchange"], entry["symbol"], entry.get("direction"), entry["decision"],
                entry.get("reason"), entry.get("strategy_id"), entry.get("strategy_name"),
                json.dumps(entry.get("lesson_ids", [])), entry.get("confidence"),
                entry.get("market_state"), entry.get("session"), entry.get("timeframe"),
                entry.get("position_id"), json.dumps(entry.get("market_snapshot", {})), entry["created_at"],
            ),
        )
        conn.execute(
            """DELETE FROM paper_decision_log WHERE id NOT IN (
                 SELECT id FROM paper_decision_log ORDER BY id DESC LIMIT 2000
               )"""
        )


def list_paper_decisions(decision=None, limit=100, since=None):
    query = "SELECT id, exchange, symbol, direction, decision, reason, strategy_id, strategy_name, " \
            "lesson_ids_json, confidence, market_state, session, timeframe, position_id, " \
            "market_snapshot_json, created_at FROM paper_decision_log"
    conditions = []
    params = []
    if decision:
        conditions.append("decision = ?")
        params.append(decision)
    if since:
        conditions.append("created_at >= ?")
        params.append(since)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    cols = ["id", "exchange", "symbol", "direction", "decision", "reason", "strategy_id", "strategy_name",
            "lesson_ids_json", "confidence", "market_state", "session", "timeframe", "position_id",
            "market_snapshot_json", "created_at"]
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    result = []
    for r in rows:
        d = dict(zip(cols, r))
        d["lesson_ids"] = json.loads(d.pop("lesson_ids_json")) if d.get("lesson_ids_json") else []
        d["market_snapshot"] = json.loads(d.pop("market_snapshot_json")) if d.get("market_snapshot_json") else {}
        result.append(d)
    return result


def update_paper_strategy_performance(strategy_id, strategy_name, pnl, is_win, rr, now_iso):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT trades, wins, losses, total_pnl, avg_rr FROM paper_strategy_performance WHERE strategy_id=?",
            (strategy_id,),
        ).fetchone()
        trades, wins, losses, total_pnl, avg_rr = row if row else (0, 0, 0, 0.0, None)
        trades += 1
        wins += 1 if is_win else 0
        losses += 0 if is_win else 1
        total_pnl += pnl
        if rr is not None:
            avg_rr = rr if avg_rr is None else (avg_rr * (trades - 1) + rr) / trades
        win_rate = (wins / trades * 100) if trades else 0.0
        score = round(win_rate * 0.5 + (avg_rr or 0) * 10 + min(total_pnl, 1000) * 0.01, 2)
        conn.execute(
            """INSERT INTO paper_strategy_performance
               (strategy_id, strategy_name, trades, wins, losses, total_pnl, avg_rr, score, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(strategy_id) DO UPDATE SET
                 strategy_name=excluded.strategy_name, trades=excluded.trades, wins=excluded.wins,
                 losses=excluded.losses, total_pnl=excluded.total_pnl, avg_rr=excluded.avg_rr,
                 score=excluded.score, updated_at=excluded.updated_at""",
            (strategy_id, strategy_name, trades, wins, losses, total_pnl, avg_rr, score, now_iso),
        )


def list_paper_strategy_performance():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT strategy_id, strategy_name, trades, wins, losses, total_pnl, avg_rr, score, updated_at "
            "FROM paper_strategy_performance ORDER BY score DESC"
        ).fetchall()
    cols = ["strategy_id", "strategy_name", "trades", "wins", "losses", "total_pnl", "avg_rr", "score", "updated_at"]
    return [dict(zip(cols, r)) for r in rows]


def update_paper_lesson_performance(lesson_id, lesson_title, pnl, is_win, confidence, now_iso):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT usage_count, wins, losses, total_pnl, confidence_avg FROM paper_lesson_performance WHERE lesson_id=?",
            (lesson_id,),
        ).fetchone()
        usage, wins, losses, total_pnl, conf_avg = row if row else (0, 0, 0, 0.0, None)
        usage += 1
        wins += 1 if is_win else 0
        losses += 0 if is_win else 1
        total_pnl += pnl
        if confidence is not None:
            conf_avg = confidence if conf_avg is None else (conf_avg * (usage - 1) + confidence) / usage
        win_rate = (wins / usage * 100) if usage else 0.0
        score = round(win_rate * 0.5 + (conf_avg or 0) * 0.3 + min(total_pnl, 1000) * 0.01, 2)
        conn.execute(
            """INSERT INTO paper_lesson_performance
               (lesson_id, lesson_title, usage_count, wins, losses, total_pnl, confidence_avg, score, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(lesson_id) DO UPDATE SET
                 lesson_title=excluded.lesson_title, usage_count=excluded.usage_count, wins=excluded.wins,
                 losses=excluded.losses, total_pnl=excluded.total_pnl, confidence_avg=excluded.confidence_avg,
                 score=excluded.score, updated_at=excluded.updated_at""",
            (lesson_id, lesson_title, usage, wins, losses, total_pnl, conf_avg, score, now_iso),
        )


def list_paper_lesson_performance():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT lesson_id, lesson_title, usage_count, wins, losses, total_pnl, confidence_avg, score, updated_at "
            "FROM paper_lesson_performance ORDER BY score DESC"
        ).fetchall()
    cols = ["lesson_id", "lesson_title", "usage_count", "wins", "losses", "total_pnl", "confidence_avg", "score", "updated_at"]
    return [dict(zip(cols, r)) for r in rows]


def get_paper_strategy_config(strategy_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT strategy_id, enabled, priority, supported_coins_json, supported_market_types_json, updated_at "
            "FROM paper_strategy_config WHERE strategy_id=?", (strategy_id,),
        ).fetchone()
    if not row:
        # Opt-in, not opt-out: a strategy with no Paper Trading config yet
        # has never been deliberately activated (e.g. via the automation
        # pipeline's handoff, which explicitly enables it), so it must not
        # silently start trading just by existing in the library -- this
        # matters much more now that multiple strategies can run at once
        # (previously the pipeline's only_strategy_id scoping masked this
        # default, since exactly one strategy was ever active regardless).
        return {"strategy_id": strategy_id, "enabled": False, "priority": 5,
                "supported_coins": [], "supported_market_types": []}
    return {
        "strategy_id": row[0], "enabled": bool(row[1]), "priority": row[2],
        "supported_coins": json.loads(row[3]) if row[3] else [],
        "supported_market_types": json.loads(row[4]) if row[4] else [],
        "updated_at": row[5],
    }


def list_paper_strategy_configs():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT strategy_id, enabled, priority, supported_coins_json, supported_market_types_json, updated_at "
            "FROM paper_strategy_config"
        ).fetchall()
    return {
        r[0]: {
            "strategy_id": r[0], "enabled": bool(r[1]), "priority": r[2],
            "supported_coins": json.loads(r[3]) if r[3] else [],
            "supported_market_types": json.loads(r[4]) if r[4] else [],
            "updated_at": r[5],
        } for r in rows
    }


def save_paper_strategy_config(strategy_id, enabled, priority, supported_coins, supported_market_types, now_iso):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO paper_strategy_config
               (strategy_id, enabled, priority, supported_coins_json, supported_market_types_json, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(strategy_id) DO UPDATE SET
                 enabled=excluded.enabled, priority=excluded.priority,
                 supported_coins_json=excluded.supported_coins_json,
                 supported_market_types_json=excluded.supported_market_types_json,
                 updated_at=excluded.updated_at""",
            (strategy_id, int(enabled), priority, json.dumps(supported_coins or []),
             json.dumps(supported_market_types or []), now_iso),
        )


def get_paper_strategy_override(strategy_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT strategy_id, manual_alert, note, updated_at FROM paper_strategy_overrides WHERE strategy_id=?",
            (strategy_id,),
        ).fetchone()
    if not row:
        return {"strategy_id": strategy_id, "manual_alert": False, "note": None, "updated_at": None}
    return {"strategy_id": row[0], "manual_alert": bool(row[1]), "note": row[2], "updated_at": row[3]}


def list_paper_strategy_overrides():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT strategy_id, manual_alert, note, updated_at FROM paper_strategy_overrides"
        ).fetchall()
    return {
        r[0]: {"strategy_id": r[0], "manual_alert": bool(r[1]), "note": r[2], "updated_at": r[3]}
        for r in rows
    }


def save_paper_strategy_override(strategy_id, manual_alert, note, now_iso):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO paper_strategy_overrides (strategy_id, manual_alert, note, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(strategy_id) DO UPDATE SET
                 manual_alert=excluded.manual_alert, note=excluded.note, updated_at=excluded.updated_at""",
            (strategy_id, int(manual_alert), note, now_iso),
        )


def create_paper_alert(alert_type, strategy_id, strategy_name, message, severity, now_iso):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO paper_alerts (alert_type, strategy_id, strategy_name, message, severity, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (alert_type, strategy_id, strategy_name, message, severity, now_iso),
        )


def list_paper_alerts(limit=50):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, alert_type, strategy_id, strategy_name, message, severity, created_at "
            "FROM paper_alerts ORDER BY created_at DESC LIMIT ?", (limit,),
        ).fetchall()
    return [
        {"id": r[0], "alert_type": r[1], "strategy_id": r[2], "strategy_name": r[3],
         "message": r[4], "severity": r[5], "created_at": r[6]}
        for r in rows
    ]


def get_recent_paper_alert(alert_type, strategy_id, since_iso):
    """Most recent alert of this type/strategy at or after since_iso, or None
    -- used to avoid re-flagging the same condition on every single poll."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM paper_alerts WHERE alert_type=? AND strategy_id IS ? AND created_at >= ? "
            "ORDER BY created_at DESC LIMIT 1",
            (alert_type, strategy_id, since_iso),
        ).fetchone()
    return row is not None


def list_paper_session_stats(since_iso=None, until_iso=None, strategy_id=None):
    """Closed-trade performance grouped by trading session (asian/london/ny/
    etc, as classified at entry time) -- time-of-day performance split."""
    query = ("SELECT session, COUNT(*), COALESCE(SUM(pnl),0), SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END) "
             "FROM paper_positions WHERE status='closed' AND pnl IS NOT NULL AND session IS NOT NULL")
    params = []
    if since_iso:
        query += " AND closed_at >= ?"
        params.append(since_iso)
    if until_iso:
        query += " AND closed_at < ?"
        params.append(until_iso)
    if strategy_id:
        query += " AND strategy_id = ?"
        params.append(strategy_id)
    query += " GROUP BY session ORDER BY SUM(pnl) DESC"
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [
        {"session": r[0], "closed_trades": r[1], "total_pnl": r[2],
         "win_rate": round(r[3] / r[1] * 100, 2) if r[1] else 0.0}
        for r in rows
    ]


def list_paper_coin_stats_by_strategy(strategy_id, since_iso=None, until_iso=None):
    """Same shape as list_paper_coin_stats but scoped to one strategy's own
    book -- Coin-Wise Performance Split per strategy."""
    query = ("SELECT symbol, COUNT(*), COALESCE(SUM(pnl),0), SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END) "
             "FROM paper_positions WHERE status='closed' AND pnl IS NOT NULL AND strategy_id = ?")
    params = [strategy_id]
    if since_iso:
        query += " AND closed_at >= ?"
        params.append(since_iso)
    if until_iso:
        query += " AND closed_at < ?"
        params.append(until_iso)
    query += " GROUP BY symbol ORDER BY SUM(pnl) DESC"
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [
        {"symbol": r[0], "closed_trades": r[1], "total_pnl": r[2],
         "win_rate": round(r[3] / r[1] * 100, 2) if r[1] else 0.0}
        for r in rows
    ]


def list_paper_coin_pattern_memory(strategy_id=None, since=None):
    """Coin-Specific Pattern Memory: closed-trade performance grouped by
    (strategy, symbol, market_state, session) -- how has THIS strategy done
    on THIS coin under THIS kind of market before. Purely computed from
    paper_positions on read; nothing is persisted or fed back into trading
    decisions automatically."""
    query = ("SELECT strategy_id, strategy_name, symbol, market_state, session, COUNT(*), "
              "COALESCE(SUM(pnl),0), SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END) "
              "FROM paper_positions WHERE status='closed' AND pnl IS NOT NULL "
              "AND strategy_id IS NOT NULL AND market_state IS NOT NULL AND session IS NOT NULL")
    params = []
    if strategy_id:
        query += " AND strategy_id = ?"
        params.append(strategy_id)
    if since:
        query += " AND created_at >= ?"
        params.append(since)
    query += " GROUP BY strategy_id, symbol, market_state, session ORDER BY COUNT(*) DESC"
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [
        {"strategy_id": r[0], "strategy_name": r[1], "symbol": r[2], "market_state": r[3],
         "session": r[4], "trades": r[5], "total_pnl": r[6],
         "win_rate": round(r[7] / r[5] * 100, 2) if r[5] else 0.0}
        for r in rows
    ]


def list_paper_closed_trades_ordered(strategy_id=None, limit=500, since=None):
    """Closed trades ordered oldest-to-newest for streak/pattern analysis
    (separate from list_closed_paper_positions, which orders newest-first
    for display). strategy_id=None returns every strategy's trades in one
    query (each row carries its own strategy_id) -- used by
    paper_trading.insights.all_streaks() to compute every strategy's streak
    without one query per strategy."""
    query = ("SELECT id, strategy_id, symbol, pnl, closed_at FROM paper_positions "
              "WHERE status='closed' AND pnl IS NOT NULL")
    params = []
    if strategy_id:
        query += " AND strategy_id = ?"
        params.append(strategy_id)
    if since:
        query += " AND created_at >= ?"
        params.append(since)
    query += " ORDER BY closed_at ASC LIMIT ?"
    params.append(limit)
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [{"id": r[0], "strategy_id": r[1], "symbol": r[2], "pnl": r[3], "closed_at": r[4]} for r in rows]


def list_paper_pattern_trades_ordered(strategy_id, symbol, market_state, session, since=None, limit=200):
    """Closed trades for one EXACT (strategy, symbol, market_state, session)
    pattern, oldest-to-newest -- used by paper_trading.auto_avoid to compute
    a consecutive-loss streak scoped to that specific pattern (not the
    strategy's overall streak, which insights.compute_streak already
    covers)."""
    query = ("SELECT pnl, closed_at FROM paper_positions WHERE status='closed' AND pnl IS NOT NULL "
              "AND strategy_id=? AND symbol=? AND market_state=? AND session=?")
    params = [strategy_id, symbol, market_state, session]
    if since:
        query += " AND created_at >= ?"
        params.append(since)
    query += " ORDER BY closed_at ASC LIMIT ?"
    params.append(limit)
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [{"pnl": r[0], "closed_at": r[1]} for r in rows]


# --------------------------------------------------------------- Telegram Integration

def log_telegram_message(position_id, strategy_id, strategy_name, trigger_type,
                          message_text, success, error, now_iso):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO telegram_message_log
               (position_id, strategy_id, strategy_name, trigger_type, message_text, success, error, sent_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (position_id, strategy_id, strategy_name, trigger_type, message_text, int(success), error, now_iso),
        )


def list_telegram_messages(limit=100):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, position_id, strategy_id, strategy_name, trigger_type, message_text, "
            "success, error, sent_at FROM telegram_message_log ORDER BY sent_at DESC LIMIT ?", (limit,),
        ).fetchall()
    cols = ["id", "position_id", "strategy_id", "strategy_name", "trigger_type",
            "message_text", "success", "error", "sent_at"]
    return [dict(zip(cols, r)) for r in rows]


def count_telegram_messages_since(since_iso):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM telegram_message_log WHERE sent_at >= ? AND success=1", (since_iso,),
        ).fetchone()
    return row[0] if row else 0


def has_telegram_signal_for_position(position_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM telegram_message_log WHERE position_id=? AND trigger_type IN ('manual','automatic') "
            "AND success=1 LIMIT 1", (position_id,),
        ).fetchone()
    return row is not None


# --------------------------------------------------------------- Weekly Auto-Report

def save_weekly_report(period_start, period_end, report_json, report_text, now_iso):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO paper_weekly_reports (period_start, period_end, report_json, report_text, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (period_start, period_end, report_json, report_text, now_iso),
        )


def list_weekly_reports(limit=20):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, period_start, period_end, report_json, report_text, created_at "
            "FROM paper_weekly_reports ORDER BY created_at DESC LIMIT ?", (limit,),
        ).fetchall()
    return [
        {"id": r[0], "period_start": r[1], "period_end": r[2], "report_json": r[3],
         "report_text": r[4], "created_at": r[5]}
        for r in rows
    ]


def get_latest_weekly_report():
    with get_conn() as conn:
        row = conn.execute(
            "SELECT created_at FROM paper_weekly_reports ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    return row[0] if row else None


# --------------------------------------------------------------- Strategy Graveyard

def bury_strategy(strategy_id, strategy_name, reason_category, reason_detail, concepts_used, now_iso):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO strategy_graveyard
               (strategy_id, strategy_name, reason_category, reason_detail, concepts_used_json, buried_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (strategy_id, strategy_name, reason_category, reason_detail, json.dumps(concepts_used or []), now_iso),
        )


def list_graveyard(limit=100):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, strategy_id, strategy_name, reason_category, reason_detail, concepts_used_json, buried_at "
            "FROM strategy_graveyard ORDER BY buried_at DESC LIMIT ?", (limit,),
        ).fetchall()
    return [
        {"id": r[0], "strategy_id": r[1], "strategy_name": r[2], "reason_category": r[3],
         "reason_detail": r[4], "concepts_used": json.loads(r[5]) if r[5] else [], "buried_at": r[6]}
        for r in rows
    ]


def is_strategy_buried(strategy_id):
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM strategy_graveyard WHERE strategy_id=? LIMIT 1", (strategy_id,)).fetchone()
    return row is not None


# --------------------------------------------------------------- Pattern-Based Auto-Avoid (active)

def save_paper_auto_avoid_rule(strategy_id, strategy_name, symbol, market_state, session,
                                consecutive_losses, reason, now_iso):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO paper_auto_avoid_rules
               (strategy_id, strategy_name, symbol, market_state, session, consecutive_losses,
                reason, active, triggered_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
               ON CONFLICT(strategy_id, symbol, market_state, session) DO UPDATE SET
                 consecutive_losses=excluded.consecutive_losses, reason=excluded.reason,
                 active=1, triggered_at=excluded.triggered_at, deactivated_at=NULL""",
            (strategy_id, strategy_name, symbol, market_state, session, consecutive_losses, reason, now_iso),
        )


def is_pattern_auto_avoided(strategy_id, symbol, market_state, session):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT reason FROM paper_auto_avoid_rules WHERE strategy_id=? AND symbol=? "
            "AND market_state=? AND session=? AND active=1",
            (strategy_id, symbol, market_state, session),
        ).fetchone()
    return row[0] if row else None


def list_paper_auto_avoid_rules(active_only=False):
    query = ("SELECT id, strategy_id, strategy_name, symbol, market_state, session, "
              "consecutive_losses, reason, active, triggered_at, deactivated_at "
              "FROM paper_auto_avoid_rules")
    if active_only:
        query += " WHERE active=1"
    query += " ORDER BY triggered_at DESC"
    with get_conn() as conn:
        rows = conn.execute(query).fetchall()
    cols = ["id", "strategy_id", "strategy_name", "symbol", "market_state", "session",
            "consecutive_losses", "reason", "active", "triggered_at", "deactivated_at"]
    return [dict(zip(cols, r)) for r in rows]


def deactivate_paper_auto_avoid_rule(rule_id, now_iso):
    with get_conn() as conn:
        conn.execute(
            "UPDATE paper_auto_avoid_rules SET active=0, deactivated_at=? WHERE id=?",
            (now_iso, rule_id),
        )


# --------------------------------------------------------------- Lesson Auto-Apply (active)

def save_paper_auto_lesson(strategy_id, strategy_name, symbol, market_state, session,
                            influence, sample_size, win_rate, explanation, now_iso):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO paper_auto_lessons
               (strategy_id, strategy_name, symbol, market_state, session, influence,
                sample_size, win_rate, explanation, active, applied_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
               ON CONFLICT(strategy_id, symbol, market_state, session) DO UPDATE SET
                 influence=excluded.influence, sample_size=excluded.sample_size,
                 win_rate=excluded.win_rate, explanation=excluded.explanation,
                 active=1, applied_at=excluded.applied_at, deactivated_at=NULL""",
            (strategy_id, strategy_name, symbol, market_state, session, influence,
             sample_size, win_rate, explanation, now_iso),
        )


def get_paper_auto_lesson(strategy_id, symbol, market_state, session):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT influence, win_rate, explanation FROM paper_auto_lessons "
            "WHERE strategy_id=? AND symbol=? AND market_state=? AND session=? AND active=1",
            (strategy_id, symbol, market_state, session),
        ).fetchone()
    return {"influence": row[0], "win_rate": row[1], "explanation": row[2]} if row else None


def list_paper_auto_lessons(active_only=False):
    query = ("SELECT id, strategy_id, strategy_name, symbol, market_state, session, influence, "
              "sample_size, win_rate, explanation, active, applied_at, deactivated_at "
              "FROM paper_auto_lessons")
    if active_only:
        query += " WHERE active=1"
    query += " ORDER BY applied_at DESC"
    with get_conn() as conn:
        rows = conn.execute(query).fetchall()
    cols = ["id", "strategy_id", "strategy_name", "symbol", "market_state", "session", "influence",
            "sample_size", "win_rate", "explanation", "active", "applied_at", "deactivated_at"]
    return [dict(zip(cols, r)) for r in rows]


def deactivate_paper_auto_lesson(lesson_id, now_iso):
    with get_conn() as conn:
        conn.execute(
            "UPDATE paper_auto_lessons SET active=0, deactivated_at=? WHERE id=?",
            (now_iso, lesson_id),
        )


# --------------------------------------------------------------- Drawdown Protection (strategy pause)

def set_strategy_paused(strategy_id, paused, reason, now_iso):
    """Ensures a paper_strategy_config row exists (defaults match
    save_paper_strategy_config's own enabled=1 default) before flipping the
    pause flag, so pausing a strategy that never had a config row yet still
    works instead of silently no-op'ing."""
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO paper_strategy_config (strategy_id, enabled, priority, paused, paused_reason, paused_at, updated_at)
               VALUES (?, 1, 5, ?, ?, ?, ?)
               ON CONFLICT(strategy_id) DO UPDATE SET
                 paused=excluded.paused, paused_reason=excluded.paused_reason,
                 paused_at=excluded.paused_at, updated_at=excluded.updated_at""",
            (strategy_id, int(paused), reason if paused else None, now_iso if paused else None, now_iso),
        )


def is_strategy_paused(strategy_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT paused, paused_reason, paused_at FROM paper_strategy_config WHERE strategy_id=?",
            (strategy_id,),
        ).fetchone()
    if not row or not row[0]:
        return False, None, None
    return True, row[1], row[2]


def list_paused_strategies():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT strategy_id, paused_reason, paused_at FROM paper_strategy_config WHERE paused=1"
        ).fetchall()
    return [{"strategy_id": r[0], "reason": r[1], "paused_at": r[2]} for r in rows]


def save_paper_lesson_candidate(strategy_id, strategy_name, symbol, market_state, session,
                                 pattern_description, sample_size, win_rate, total_pnl, now_iso):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO paper_lesson_candidates
               (strategy_id, strategy_name, symbol, market_state, session, pattern_description,
                sample_size, win_rate, total_pnl, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'flagged', ?)
               ON CONFLICT(strategy_id, symbol, market_state, session) DO UPDATE SET
                 strategy_name=excluded.strategy_name, pattern_description=excluded.pattern_description,
                 sample_size=excluded.sample_size, win_rate=excluded.win_rate,
                 total_pnl=excluded.total_pnl, created_at=excluded.created_at""",
            (strategy_id, strategy_name, symbol, market_state, session, pattern_description,
             sample_size, win_rate, total_pnl, now_iso),
        )


def list_paper_lesson_candidates(status="flagged", limit=100):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, strategy_id, strategy_name, symbol, market_state, session, pattern_description, "
            "sample_size, win_rate, total_pnl, status, created_at FROM paper_lesson_candidates "
            "WHERE status=? ORDER BY created_at DESC LIMIT ?", (status, limit),
        ).fetchall()
    cols = ["id", "strategy_id", "strategy_name", "symbol", "market_state", "session",
            "pattern_description", "sample_size", "win_rate", "total_pnl", "status", "created_at"]
    return [dict(zip(cols, r)) for r in rows]


# --------------------------------------------------------------- Knowledge Compiler

def save_compiled_document(doc):
    """doc: dict with title/source_type/doc_type/classification_confidence/status/
    raw_text/sections(list)/strategy_ids(list)/lesson_ids(list)/concepts(list)/
    unresolved(list)/clarification_notes(list)/tags(list)/created_at/
    ai_assisted(bool, default False)/ai_provider(str or None)/
    hidden_rules(list of {rule,confidence,reason,evidence}, default [])/
    psychology_notes(list of str, default [])/
    deep_knowledge(dict or None -- raw AI structured payload, for audit).
    Insert-only -- a compiled document is a point-in-time record, never
    edited in place."""
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO compiled_documents
               (id, title, source_type, doc_type, classification_confidence, status,
                raw_text, sections_json, strategy_ids_json, lesson_ids_json,
                concepts_json, unresolved_json, clarification_notes_json, tags_json, created_at,
                ai_assisted, ai_provider, hidden_rules_json, psychology_notes_json, deep_knowledge_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                doc["id"], doc.get("title"), doc.get("source_type"), doc["doc_type"],
                doc.get("classification_confidence"), doc["status"], doc.get("raw_text"),
                json.dumps(doc.get("sections", [])), json.dumps(doc.get("strategy_ids", [])),
                json.dumps(doc.get("lesson_ids", [])), json.dumps(doc.get("concepts", [])),
                json.dumps(doc.get("unresolved", [])), json.dumps(doc.get("clarification_notes", [])),
                json.dumps(doc.get("tags", [])), doc["created_at"],
                1 if doc.get("ai_assisted") else 0, doc.get("ai_provider"),
                json.dumps(doc.get("hidden_rules", [])), json.dumps(doc.get("psychology_notes", [])),
                json.dumps(doc.get("deep_knowledge")) if doc.get("deep_knowledge") is not None else None,
            ),
        )


_COMPILED_DOCUMENT_COLUMNS = [
    "id", "title", "source_type", "doc_type", "classification_confidence", "status",
    "raw_text", "sections_json", "strategy_ids_json", "lesson_ids_json",
    "concepts_json", "unresolved_json", "clarification_notes_json", "tags_json", "created_at",
    "ai_assisted", "ai_provider", "hidden_rules_json", "psychology_notes_json", "deep_knowledge_json",
]


def _row_to_compiled_document(row):
    d = dict(zip(_COMPILED_DOCUMENT_COLUMNS, row))
    d["sections"] = json.loads(d.pop("sections_json")) if d.get("sections_json") else []
    d["strategy_ids"] = json.loads(d.pop("strategy_ids_json")) if d.get("strategy_ids_json") else []
    d["lesson_ids"] = json.loads(d.pop("lesson_ids_json")) if d.get("lesson_ids_json") else []
    d["concepts"] = json.loads(d.pop("concepts_json")) if d.get("concepts_json") else []
    d["unresolved"] = json.loads(d.pop("unresolved_json")) if d.get("unresolved_json") else []
    d["clarification_notes"] = json.loads(d.pop("clarification_notes_json")) if d.get("clarification_notes_json") else []
    d["tags"] = json.loads(d.pop("tags_json")) if d.get("tags_json") else []
    d["hidden_rules"] = json.loads(d.pop("hidden_rules_json")) if d.get("hidden_rules_json") else []
    d["psychology_notes"] = json.loads(d.pop("psychology_notes_json")) if d.get("psychology_notes_json") else []
    d["deep_knowledge"] = json.loads(d.pop("deep_knowledge_json")) if d.get("deep_knowledge_json") else None
    return d


def get_compiled_document(doc_id):
    with get_conn() as conn:
        row = conn.execute(
            f"SELECT {','.join(_COMPILED_DOCUMENT_COLUMNS)} FROM compiled_documents WHERE id = ?", (doc_id,)
        ).fetchone()
    return _row_to_compiled_document(row) if row else None


def list_compiled_documents(doc_type=None, status=None, limit=100):
    query = f"SELECT {','.join(_COMPILED_DOCUMENT_COLUMNS)} FROM compiled_documents"
    clauses, params = [], []
    if doc_type:
        clauses.append("doc_type = ?")
        params.append(doc_type)
    if status:
        clauses.append("status = ?")
        params.append(status)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_compiled_document(r) for r in rows]


def touch_knowledge_concept(canonical_name, category, aliases, now_iso):
    """Auto-growing usage tracker for dictionary terms actually seen in
    compiled documents -- the static Trading Dictionary itself stays
    code-defined; this just records real usage for the Concepts view."""
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO knowledge_concepts (canonical_name, category, aliases_json, usage_count, first_seen_at, last_seen_at)
               VALUES (?, ?, ?, 1, ?, ?)
               ON CONFLICT(canonical_name) DO UPDATE SET
                 usage_count = usage_count + 1, last_seen_at = excluded.last_seen_at""",
            (canonical_name, category, json.dumps(aliases or []), now_iso, now_iso),
        )


def list_knowledge_concepts():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT canonical_name, category, aliases_json, usage_count, first_seen_at, last_seen_at "
            "FROM knowledge_concepts ORDER BY usage_count DESC"
        ).fetchall()
    return [
        {
            "canonical_name": r[0], "category": r[1],
            "aliases": json.loads(r[2]) if r[2] else [],
            "usage_count": r[3], "first_seen_at": r[4], "last_seen_at": r[5],
        }
        for r in rows
    ]


def save_condition_report(batch_id, symbol, timeframe, report, now_iso):
    """report: the dict produced by backtest_engine.diagnostics.condition_hit_report.
    Insert-or-replace -- a re-run of the same (batch_id, symbol, timeframe)
    combo (e.g. after a resume) simply overwrites its own prior report."""
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO backtest_condition_reports (batch_id, symbol, timeframe, report_json, created_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(batch_id, symbol, timeframe) DO UPDATE SET
                 report_json=excluded.report_json, created_at=excluded.created_at""",
            (batch_id, symbol, timeframe, json.dumps(report), now_iso),
        )


def get_condition_report(batch_id, symbol, timeframe):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT report_json FROM backtest_condition_reports WHERE batch_id=? AND symbol=? AND timeframe=?",
            (batch_id, symbol, timeframe),
        ).fetchone()
    return json.loads(row[0]) if row else None


def list_condition_reports(batch_id):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT symbol, timeframe, report_json, created_at FROM backtest_condition_reports WHERE batch_id=?",
            (batch_id,),
        ).fetchall()
    return [{"symbol": r[0], "timeframe": r[1], "report": json.loads(r[2]), "created_at": r[3]} for r in rows]


# --------------------------------------------------------------- AI Integration Center

def save_ai_usage_log(provider, model, endpoint, status, now_iso,
                       tokens_in=None, tokens_out=None, latency_ms=None, error_message=None):
    """One row per AI provider call attempt (success or failure) -- used by
    the AI Integration Center's View Usage / View Logs panels. Never raises;
    callers (ai_integration/*) treat logging as best-effort."""
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO ai_usage_log
               (provider, model, endpoint, status, tokens_in, tokens_out, latency_ms, error_message, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (provider, model, endpoint, status, tokens_in, tokens_out, latency_ms, error_message, now_iso),
        )


def list_ai_usage_log(provider=None, limit=200):
    query = "SELECT id, provider, model, endpoint, status, tokens_in, tokens_out, latency_ms, error_message, created_at FROM ai_usage_log"
    params = []
    if provider:
        query += " WHERE provider = ?"
        params.append(provider)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [
        {
            "id": r[0], "provider": r[1], "model": r[2], "endpoint": r[3], "status": r[4],
            "tokens_in": r[5], "tokens_out": r[6], "latency_ms": r[7], "error_message": r[8], "created_at": r[9],
        }
        for r in rows
    ]


def ai_usage_summary():
    """Aggregate call counts/tokens per provider -- feeds the AI Center's
    usage cards without needing to pull every raw log row client-side."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT provider,
                      COUNT(*) AS total_calls,
                      SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS success_calls,
                      SUM(CASE WHEN status!='success' THEN 1 ELSE 0 END) AS failed_calls,
                      COALESCE(SUM(tokens_in), 0) AS tokens_in,
                      COALESCE(SUM(tokens_out), 0) AS tokens_out,
                      COALESCE(AVG(latency_ms), 0) AS avg_latency_ms,
                      COALESCE(AVG(tokens_in + tokens_out), 0) AS avg_tokens,
                      MAX(created_at) AS last_used_at
               FROM ai_usage_log GROUP BY provider"""
        ).fetchall()
    return [
        {
            "provider": r[0], "total_calls": r[1], "success_calls": r[2], "failed_calls": r[3],
            "tokens_in": r[4], "tokens_out": r[5], "avg_latency_ms": round(r[6], 1),
            "avg_tokens": round(r[7], 1), "last_used_at": r[8],
        }
        for r in rows
    ]


def ai_usage_since(since_iso):
    """Per-provider call/token counts for ai_usage_log rows with
    created_at >= since_iso -- ISO8601 timestamps sort lexicographically, so
    a plain string comparison is exact and index-friendly. Used for the
    Usage Monitor's 'today' / 'this month' cards and quota tracking."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT provider,
                      COUNT(*) AS total_calls,
                      COALESCE(SUM(tokens_in), 0) AS tokens_in,
                      COALESCE(SUM(tokens_out), 0) AS tokens_out
               FROM ai_usage_log WHERE created_at >= ? GROUP BY provider""",
            (since_iso,),
        ).fetchall()
    return {r[0]: {"total_calls": r[1], "tokens_in": r[2], "tokens_out": r[3]} for r in rows}


_QUEUE_COLUMNS = [
    "id", "title", "source_hint", "filename", "raw_text", "use_ai", "status",
    "result_doc_id", "ai_assisted", "ai_provider", "error_message", "processing_time_ms",
    "created_at", "started_at", "finished_at", "input_kind", "content_type",
]


def _row_to_queue_item(row):
    d = dict(zip(_QUEUE_COLUMNS, row))
    d["use_ai"] = bool(d["use_ai"])
    d["ai_assisted"] = bool(d["ai_assisted"]) if d["ai_assisted"] is not None else None
    d["input_kind"] = d.get("input_kind") or "text"
    return d


def enqueue_ai_import(item_id, title, source_hint, filename, raw_text, use_ai, now_iso, input_kind="text", content_type=None):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO ai_import_queue (id, title, source_hint, filename, raw_text, use_ai, status, created_at, input_kind, content_type)
               VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)""",
            (item_id, title, source_hint, filename, raw_text, 1 if use_ai else 0, now_iso, input_kind, content_type),
        )


def update_ai_import_queue(item_id, **fields):
    """fields may include: status, result_doc_id, ai_assisted, ai_provider,
    error_message, processing_time_ms, started_at, finished_at."""
    if not fields:
        return
    allowed = {"status", "result_doc_id", "ai_assisted", "ai_provider", "error_message",
               "processing_time_ms", "started_at", "finished_at"}
    set_clauses, params = [], []
    for key, value in fields.items():
        if key not in allowed:
            continue
        if key == "ai_assisted" and value is not None:
            value = 1 if value else 0
        set_clauses.append(f"{key} = ?")
        params.append(value)
    if not set_clauses:
        return
    params.append(item_id)
    with get_conn() as conn:
        conn.execute(f"UPDATE ai_import_queue SET {', '.join(set_clauses)} WHERE id = ?", params)


def get_ai_import_queue_item(item_id):
    with get_conn() as conn:
        row = conn.execute(
            f"SELECT {','.join(_QUEUE_COLUMNS)} FROM ai_import_queue WHERE id = ?", (item_id,)
        ).fetchone()
    return _row_to_queue_item(row) if row else None


def list_ai_import_queue(status=None, limit=100):
    query = f"SELECT {','.join(_QUEUE_COLUMNS)} FROM ai_import_queue"
    params = []
    if status:
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_queue_item(r) for r in rows]


def ai_import_queue_stats():
    """Aggregate status counts for the CEO Dashboard's success-rate/failed-
    imports cards, without pulling every queue row client-side."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) FROM ai_import_queue GROUP BY status"
        ).fetchall()
    counts = {"pending": 0, "processing": 0, "completed": 0, "failed": 0}
    counts.update({r[0]: r[1] for r in rows})
    total_finished = counts["completed"] + counts["failed"]
    success_rate = round(counts["completed"] / total_finished * 100, 1) if total_finished else None
    return {**counts, "success_rate_pct": success_rate}


def claim_next_pending_ai_import():
    """Atomically claims the oldest pending queue row by flipping it to
    'processing' in the same transaction as the SELECT, so two worker
    threads (or a worker plus a restart) can never both pick up the same
    item. Returns the claimed item dict, or None if the queue is empty."""
    with get_conn() as conn:
        row = conn.execute(
            f"SELECT {','.join(_QUEUE_COLUMNS)} FROM ai_import_queue WHERE status='pending' ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        item = _row_to_queue_item(row)
        conn.execute("UPDATE ai_import_queue SET status='processing' WHERE id = ? AND status='pending'", (item["id"],))
    return item


def save_ai_dictionary_entry(
    canonical_name, definition, keywords, category, source_doc_id, now_iso,
    aliases=None, examples=None, related_concepts=None, usage_notes=None,
):
    """Insert-or-update: a term seen again from a new document refreshes its
    definition/keywords/aliases/examples/related_concepts/usage_notes/updated_at
    but keeps the original created_at and source_doc_id (first-seen
    provenance). aliases/examples/related_concepts/usage_notes are optional --
    the deterministic acronym-scan discovery path (no AI involved) only ever
    supplies canonical_name/definition/keywords/category, exactly as before."""
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO ai_dictionary_entries
               (canonical_name, definition, keywords_json, category, source_doc_id, created_at, updated_at,
                aliases_json, examples_json, related_concepts_json, usage_notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(canonical_name) DO UPDATE SET
                 definition=excluded.definition, keywords_json=excluded.keywords_json,
                 category=excluded.category, updated_at=excluded.updated_at,
                 aliases_json=excluded.aliases_json, examples_json=excluded.examples_json,
                 related_concepts_json=excluded.related_concepts_json, usage_notes=excluded.usage_notes""",
            (
                canonical_name, definition, json.dumps(keywords or []), category, source_doc_id, now_iso, now_iso,
                json.dumps(aliases or []), json.dumps(examples or []), json.dumps(related_concepts or []),
                usage_notes,
            ),
        )


_AI_DICT_COLUMNS = [
    "canonical_name", "definition", "keywords_json", "category", "source_doc_id", "created_at", "updated_at",
    "aliases_json", "examples_json", "related_concepts_json", "usage_notes",
]


def _row_to_ai_dictionary_entry(row):
    d = dict(zip(_AI_DICT_COLUMNS, row))
    d["keywords"] = json.loads(d.pop("keywords_json")) if d.get("keywords_json") else []
    d["aliases"] = json.loads(d.pop("aliases_json")) if d.get("aliases_json") else []
    d["examples"] = json.loads(d.pop("examples_json")) if d.get("examples_json") else []
    d["related_concepts"] = json.loads(d.pop("related_concepts_json")) if d.get("related_concepts_json") else []
    return d


def get_ai_dictionary_entry(canonical_name):
    with get_conn() as conn:
        row = conn.execute(
            f"SELECT {','.join(_AI_DICT_COLUMNS)} FROM ai_dictionary_entries WHERE canonical_name = ?",
            (canonical_name,),
        ).fetchone()
    return _row_to_ai_dictionary_entry(row) if row else None


def list_ai_dictionary_entries():
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT {','.join(_AI_DICT_COLUMNS)} FROM ai_dictionary_entries ORDER BY canonical_name ASC"
        ).fetchall()
    return [_row_to_ai_dictionary_entry(r) for r in rows]


def get_ai_import_cache(content_hash):
    """v8: pre-AI dedup lookup -- if this exact document (by normalized
    content hash) was already understood by AI before, the same structured
    result (ai_result dict, JSON-encoded) is returned so the caller can
    build/save the strategy/lessons through the normal path WITHOUT calling
    any AI provider again. Returns (ai_result_dict, provider) or (None, None)
    on a cache miss."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT ai_result_json, provider FROM ai_import_cache WHERE content_hash = ?", (content_hash,)
        ).fetchone()
    if not row or not row[0]:
        return None, None
    return json.loads(row[0]), row[1]


def save_ai_import_cache(content_hash, ai_result, provider, now_iso):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO ai_import_cache (content_hash, ai_result_json, provider, created_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(content_hash) DO UPDATE SET
                 ai_result_json=excluded.ai_result_json, provider=excluded.provider, created_at=excluded.created_at""",
            (content_hash, json.dumps(ai_result), provider, now_iso),
        )


def save_knowledge_relationship(from_type, from_id, to_type, to_id, relation, now_iso):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO knowledge_relationships (from_type, from_id, to_type, to_id, relation, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (from_type, from_id, to_type, to_id, relation, now_iso),
        )


def list_knowledge_relationships(from_id=None, to_id=None):
    query = "SELECT id, from_type, from_id, to_type, to_id, relation, created_at FROM knowledge_relationships"
    clauses, params = [], []
    if from_id:
        clauses.append("from_id = ?")
        params.append(from_id)
    if to_id:
        clauses.append("to_id = ?")
        params.append(to_id)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY id DESC"
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [
        {"id": r[0], "from_type": r[1], "from_id": r[2], "to_type": r[3], "to_id": r[4], "relation": r[5], "created_at": r[6]}
        for r in rows
    ]


# ==================================================================
# Phase 7A -- Evolution Core Engine + SINDHU Strategy Generator
# BOT-owned storage only: see the _SCHEMA comment above bot_strategies
# for why this is a physically separate set of tables from
# strategy_library's user-owned files and the user-authored `lessons` table.
# ==================================================================

_BOT_STRATEGY_COLUMNS = [
    "id", "base_id", "generation", "parent_id", "name", "config_json", "dna_json",
    "origin", "made_with_ai", "status", "evolution_score", "score_breakdown_json",
    "backtest_summary_json", "mutation_reason", "created_at", "updated_at",
]


def _row_to_bot_strategy(row):
    d = dict(zip(_BOT_STRATEGY_COLUMNS, row))
    d["made_with_ai"] = bool(d["made_with_ai"])
    d["config"] = json.loads(d.pop("config_json"))
    d["dna"] = json.loads(d.pop("dna_json")) if d.get("dna_json") else []
    d["score_breakdown"] = json.loads(d.pop("score_breakdown_json")) if d.get("score_breakdown_json") else None
    d["backtest_summary"] = json.loads(d.pop("backtest_summary_json")) if d.get("backtest_summary_json") else None
    return d


def create_bot_strategy(id, base_id, generation, parent_id, name, config_dict, dna_tags,
                         origin, made_with_ai, mutation_reason, now_iso):
    """A brand-new BOT strategy row -- either generation 1 of a new lineage
    (parent_id=None) or a new generation of an existing one. Never updates
    or replaces an existing row; every call is a fresh INSERT, which is what
    makes "every generation is stored permanently" (A.4) true by
    construction rather than by discipline."""
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO bot_strategies
               (id, base_id, generation, parent_id, name, config_json, dna_json, origin,
                made_with_ai, status, evolution_score, score_breakdown_json,
                backtest_summary_json, mutation_reason, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', NULL, NULL, NULL, ?, ?, ?)""",
            (id, base_id, generation, parent_id, name, json.dumps(config_dict), json.dumps(dna_tags or []),
             origin, 1 if made_with_ai else 0, mutation_reason, now_iso, now_iso),
        )


def update_bot_strategy_result(id, evolution_score=None, score_breakdown=None, backtest_summary=None, now_iso=None):
    fields, values = ["updated_at = ?"], [now_iso]
    if evolution_score is not None:
        fields.append("evolution_score = ?")
        values.append(evolution_score)
    if score_breakdown is not None:
        fields.append("score_breakdown_json = ?")
        values.append(json.dumps(score_breakdown))
    if backtest_summary is not None:
        fields.append("backtest_summary_json = ?")
        values.append(json.dumps(backtest_summary))
    values.append(id)
    with get_conn() as conn:
        conn.execute(f"UPDATE bot_strategies SET {', '.join(fields)} WHERE id = ?", values)


def archive_bot_strategy(id, now_iso):
    """Archival is a status flip, never a DELETE -- see A.9/A.4: no
    generation or lineage may ever be destroyed."""
    with get_conn() as conn:
        conn.execute("UPDATE bot_strategies SET status='archived', updated_at=? WHERE id=?", (now_iso, id))


def get_bot_strategy(id):
    with get_conn() as conn:
        row = conn.execute(
            f"SELECT {','.join(_BOT_STRATEGY_COLUMNS)} FROM bot_strategies WHERE id=?", (id,)
        ).fetchone()
    return _row_to_bot_strategy(row) if row else None


def list_bot_strategies(base_id=None, origin=None, status=None, limit=500):
    query = f"SELECT {','.join(_BOT_STRATEGY_COLUMNS)} FROM bot_strategies"
    clauses, params = [], []
    if base_id:
        clauses.append("base_id = ?")
        params.append(base_id)
    if origin:
        clauses.append("origin = ?")
        params.append(origin)
    if status:
        clauses.append("status = ?")
        params.append(status)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_bot_strategy(r) for r in rows]


def latest_generation_for_base(base_id):
    """The newest generation of one BOT strategy lineage -- what the mutator
    branches its next generation from. None if base_id has no rows yet."""
    with get_conn() as conn:
        row = conn.execute(
            f"SELECT {','.join(_BOT_STRATEGY_COLUMNS)} FROM bot_strategies "
            "WHERE base_id=? ORDER BY generation DESC LIMIT 1",
            (base_id,),
        ).fetchone()
    return _row_to_bot_strategy(row) if row else None


def list_bot_strategy_base_ids():
    with get_conn() as conn:
        rows = conn.execute("SELECT DISTINCT base_id FROM bot_strategies").fetchall()
    return [r[0] for r in rows]


_BOT_LESSON_COLUMNS = [
    "id", "base_id", "generation", "parent_id", "title", "category", "description",
    "derived_from_json", "conditions_json", "status", "confidence", "created_at", "updated_at",
]


def _row_to_bot_lesson(row):
    d = dict(zip(_BOT_LESSON_COLUMNS, row))
    d["derived_from"] = json.loads(d.pop("derived_from_json")) if d.get("derived_from_json") else {}
    d["conditions"] = json.loads(d.pop("conditions_json")) if d.get("conditions_json") else []
    return d


def create_bot_lesson(id, base_id, generation, parent_id, title, category, description,
                       derived_from, conditions, confidence, now_iso):
    """Same permanence guarantee as create_bot_strategy -- always a fresh
    INSERT, never an UPDATE, so every lesson generation (A.5) survives."""
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO bot_lessons
               (id, base_id, generation, parent_id, title, category, description,
                derived_from_json, conditions_json, status, confidence, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)""",
            (id, base_id, generation, parent_id, title, category, description,
             json.dumps(derived_from), json.dumps(conditions or []), confidence, now_iso, now_iso),
        )


def get_bot_lesson(id):
    with get_conn() as conn:
        row = conn.execute(
            f"SELECT {','.join(_BOT_LESSON_COLUMNS)} FROM bot_lessons WHERE id=?", (id,)
        ).fetchone()
    return _row_to_bot_lesson(row) if row else None


def list_bot_lessons(base_id=None, status=None, limit=500):
    query = f"SELECT {','.join(_BOT_LESSON_COLUMNS)} FROM bot_lessons"
    clauses, params = [], []
    if base_id:
        clauses.append("base_id = ?")
        params.append(base_id)
    if status:
        clauses.append("status = ?")
        params.append(status)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_bot_lesson(r) for r in rows]


def latest_generation_for_lesson_base(base_id):
    with get_conn() as conn:
        row = conn.execute(
            f"SELECT {','.join(_BOT_LESSON_COLUMNS)} FROM bot_lessons "
            "WHERE base_id=? ORDER BY generation DESC LIMIT 1",
            (base_id,),
        ).fetchone()
    return _row_to_bot_lesson(row) if row else None


def list_bot_lesson_base_ids():
    with get_conn() as conn:
        rows = conn.execute("SELECT DISTINCT base_id FROM bot_lessons").fetchall()
    return [r[0] for r in rows]


# ---- evolution_jobs: identical checkpoint/resume shape to pipeline_jobs ----

def create_evolution_job(job_id, now_iso):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO evolution_jobs (job_id, status, stage, checkpoint_json, error, created_at, updated_at)
               VALUES (?, 'running', 'starting', '{}', NULL, ?, ?)""",
            (job_id, now_iso, now_iso),
        )


def update_evolution_job(job_id, now_iso, stage=None, checkpoint=None, status=None, error=None):
    fields, values = ["updated_at = ?"], [now_iso]
    if stage is not None:
        fields.append("stage = ?")
        values.append(stage)
    if checkpoint is not None:
        fields.append("checkpoint_json = ?")
        values.append(json.dumps(checkpoint))
    if status is not None:
        fields.append("status = ?")
        values.append(status)
    if error is not None:
        fields.append("error = ?")
        values.append(error)
    values.append(job_id)
    with get_conn() as conn:
        conn.execute(f"UPDATE evolution_jobs SET {', '.join(fields)} WHERE job_id = ?", values)


def get_evolution_job(job_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT job_id, status, stage, checkpoint_json, error, created_at, updated_at "
            "FROM evolution_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "job_id": row[0], "status": row[1], "stage": row[2],
        "checkpoint": json.loads(row[3]) if row[3] else {},
        "error": row[4], "created_at": row[5], "updated_at": row[6],
    }


def list_running_evolution_jobs():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT job_id, status, stage, checkpoint_json, error, created_at, updated_at "
            "FROM evolution_jobs WHERE status = 'running'"
        ).fetchall()
    return [
        {"job_id": r[0], "status": r[1], "stage": r[2], "checkpoint": json.loads(r[3]) if r[3] else {},
         "error": r[4], "created_at": r[5], "updated_at": r[6]}
        for r in rows
    ]


def list_evolution_jobs(limit=200):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT job_id, status, stage, checkpoint_json, error, created_at, updated_at "
            "FROM evolution_jobs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {"job_id": r[0], "status": r[1], "stage": r[2], "checkpoint": json.loads(r[3]) if r[3] else {},
         "error": r[4], "created_at": r[5], "updated_at": r[6]}
        for r in rows
    ]


# ---- champion_records: append-only, "current" = most recent per category ----

def save_champion(category, value, score, details, now_iso):
    """Always an INSERT, never an UPDATE -- champion history for a category
    is the full list of rows ever written for it; "current" is just the
    newest one (get_current_champion below). Nothing is ever overwritten or
    deleted, satisfying A.9's "delete... knowledge of any version" ban."""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO champion_records (category, value, score, details_json, computed_at) VALUES (?, ?, ?, ?, ?)",
            (category, value, score, json.dumps(details or {}), now_iso),
        )


def get_current_champion(category):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT category, value, score, details_json, computed_at FROM champion_records "
            "WHERE category=? ORDER BY computed_at DESC, id DESC LIMIT 1",
            (category,),
        ).fetchone()
    if not row:
        return None
    return {"category": row[0], "value": row[1], "score": row[2],
            "details": json.loads(row[3]) if row[3] else {}, "computed_at": row[4]}


def list_current_champions():
    """One row per category -- the most recent champion computed so far in
    each. Backs the Champion Engine summary (A.7)."""
    with get_conn() as conn:
        rows = conn.execute("SELECT DISTINCT category FROM champion_records").fetchall()
    return [get_current_champion(r[0]) for r in rows]


# ---- knowledge_versions: append-only, never deleted (A.10) ----

def create_knowledge_version(reason, snapshot, now_iso):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO knowledge_versions (reason, snapshot_json, created_at) VALUES (?, ?, ?)",
            (reason, json.dumps(snapshot), now_iso),
        )
        return cur.lastrowid


def get_latest_knowledge_version():
    with get_conn() as conn:
        row = conn.execute(
            "SELECT version, reason, snapshot_json, created_at FROM knowledge_versions ORDER BY version DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None
    return {"version": row[0], "reason": row[1], "snapshot": json.loads(row[2]), "created_at": row[3]}


def list_knowledge_versions(limit=50):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT version, reason, snapshot_json, created_at FROM knowledge_versions ORDER BY version DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [{"version": r[0], "reason": r[1], "snapshot": json.loads(r[2]), "created_at": r[3]} for r in rows]


# ---- daily_generation_log: the hard 1-AI-call-per-day limiter (B.2) ----

def get_daily_generation(date):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT date, ai_calls_used, candidates_generated, updated_at FROM daily_generation_log WHERE date=?",
            (date,),
        ).fetchone()
    if not row:
        return {"date": date, "ai_calls_used": 0, "candidates_generated": 0, "updated_at": None}
    return {"date": row[0], "ai_calls_used": row[1], "candidates_generated": row[2], "updated_at": row[3]}


def _ensure_daily_generation_row(conn, date, now_iso):
    conn.execute(
        "INSERT OR IGNORE INTO daily_generation_log (date, ai_calls_used, candidates_generated, updated_at) "
        "VALUES (?, 0, 0, ?)",
        (date, now_iso),
    )


def try_reserve_ai_generation_call(date, now_iso):
    """The hard architectural guarantee behind B.2: this UPDATE can only
    ever flip ai_calls_used from 0 to 1 once per date (the WHERE clause
    makes a second attempt on the same date a no-op), so it is structurally
    impossible -- not just policy -- for more than one AI-assisted candidate
    to be produced per day, mirroring how ai_import_cache prevents a repeat
    AI call for a document already seen. Returns True iff THIS call won the
    reservation."""
    with get_conn() as conn:
        _ensure_daily_generation_row(conn, date, now_iso)
        cur = conn.execute(
            "UPDATE daily_generation_log SET ai_calls_used = 1, updated_at = ? WHERE date = ? AND ai_calls_used = 0",
            (now_iso, date),
        )
        return cur.rowcount == 1


def increment_daily_candidates_generated(date, now_iso, by=1):
    with get_conn() as conn:
        _ensure_daily_generation_row(conn, date, now_iso)
        conn.execute(
            "UPDATE daily_generation_log SET candidates_generated = candidates_generated + ?, updated_at = ? WHERE date = ?",
            (by, now_iso, date),
        )
