"""Grand Feature Expansion, Phase 3 Feature 8: confirms
data_engine.storage._migrate_paper_positions_excursion_columns() actually
heals an EXISTING SQLite database that predates the MAE/MFE columns --
CREATE TABLE IF NOT EXISTS is a no-op on a table that already exists, so
adding a column to the CREATE statement alone (without a real ALTER TABLE
migration) would never reach a real, already-running database. Found via
a genuine test failure against the real local database during this
session -- this test locks the fix in.
"""

import sqlite3

from data_engine import storage

# The real paper_positions schema exactly as it existed before this
# feature (every column _SCHEMA declares, minus lowest_price_seen/
# highest_price_seen) -- a faithful stand-in for a pre-migration database,
# not a stripped-down stub that would trip over an unrelated missing
# column (e.g. the idx_paper_positions_status_closed index needs closed_at).
_OLD_PAPER_POSITIONS_SCHEMA = """
CREATE TABLE paper_positions (
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
)
"""


def test_migration_adds_missing_columns_to_a_pre_existing_table(tmp_path, monkeypatch):
    db_path = tmp_path / "old_sindhu.db"
    monkeypatch.setattr(storage, "DB_PATH", str(db_path))

    # Simulate a database that predates this feature: create paper_positions
    # WITHOUT the new columns (a stand-in for the old schema), with one
    # real row already in it.
    conn = sqlite3.connect(str(db_path))
    conn.execute(_OLD_PAPER_POSITIONS_SCHEMA)
    conn.execute(
        "INSERT INTO paper_positions (id, exchange, symbol, direction, entry_price, size, entry_time, status, created_at) "
        "VALUES ('old1', 'binance', 'BTCUSDT', 'long', 100.0, 1.0, 1700000000000, 'open', '2026-01-01T00:00:00+00:00')"
    )
    conn.commit()
    conn.close()

    storage.init_db()  # must not error, and must add the missing columns

    with storage.get_conn() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(paper_positions)").fetchall()}
    assert "lowest_price_seen" in cols
    assert "highest_price_seen" in cols


def test_pre_existing_rows_are_backfilled_to_entry_price_not_left_null(tmp_path, monkeypatch):
    db_path = tmp_path / "old_sindhu.db"
    monkeypatch.setattr(storage, "DB_PATH", str(db_path))

    conn = sqlite3.connect(str(db_path))
    conn.execute(_OLD_PAPER_POSITIONS_SCHEMA)
    conn.execute(
        "INSERT INTO paper_positions (id, exchange, symbol, direction, entry_price, size, entry_time, status, created_at) "
        "VALUES ('old1', 'binance', 'BTCUSDT', 'long', 123.45, 1.0, 1700000000000, 'closed', '2026-01-01T00:00:00+00:00')"
    )
    conn.commit()
    conn.close()

    storage.init_db()

    pos = storage.get_paper_position("old1")
    assert pos["lowest_price_seen"] == 123.45
    assert pos["highest_price_seen"] == 123.45
    assert pos["mae_amount"] == 0.0  # honestly reports "no excursion recorded" for a pre-migration trade
    assert pos["mfe_amount"] == 0.0


def test_running_init_db_twice_is_a_safe_no_op(tmp_path, monkeypatch):
    db_path = tmp_path / "sindhu.db"
    monkeypatch.setattr(storage, "DB_PATH", str(db_path))
    storage.init_db()
    storage.init_db()  # must not raise "duplicate column" or similar
