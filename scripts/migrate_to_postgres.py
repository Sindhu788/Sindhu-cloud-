"""One-off migration: copies ONLY the lightweight cloud runner's own
tables from the real local SQLite database into a Postgres database
(Railway's, or any other), so the cloud runner starts with the CEO's
real strategy configs, open positions, and trading history instead of an
empty account.

Deliberately copies EXACTLY the curated tables in
data_engine/db_backend.py's POSTGRES_SCHEMA -- the same tables the cloud
runner's own code path touches (paper_positions, paper_account_state,
paper_strategy_config, telegram_message_log, and so on). It does NOT
touch, read, or migrate klines_1m, backtest_batches/backtest_results/
backtest_trades, ai_* extraction tables, or the evolution Governor's own
tables -- those make up the vast majority of the real database's 45+ GB
and the lightweight cloud runner never queries them.

Row filtering: copies ALL rows in each curated table, not just rows for
currently-ENABLED strategies. A strategy that is temporarily paused or
disabled still keeps its real historical PnL/trade record everywhere
else in this project ("archive, never delete") -- silently dropping its
rows here just because paper_strategy_config.enabled happens to be 0
today would contradict that and could not be undone. The curated tables
are small regardless (a few hundred rows each on the real database, not
millions), so there is no size reason to filter.

Idempotent and safe to re-run: every insert is `ON CONFLICT DO NOTHING`
keyed on each table's real primary key, so running this twice (e.g. after
migrating once, trading locally a bit more, then migrating again) only
adds rows that do not already exist in Postgres -- it never overwrites or
duplicates a row already there. Read-only against the source SQLite file
(never opened via data_engine.storage.get_conn(), which would apply
SQLite's own migrations to it) -- opened directly, read-only, so a
mistake in this script can never corrupt the real local database.

USAGE (run from the local laptop, which has the real SQLite database):

    DATABASE_URL="postgresql://...the Railway Postgres connection string..." \\
        python scripts/migrate_to_postgres.py

DATABASE_URL must be a connection string reachable FROM the laptop -- that
is Railway's "public" / "external" Postgres connection string (from the
Postgres service's Connect tab), not the "private"/internal one (which
only resolves inside Railway's own network). See RAILWAY_DEPLOY.md.

Never hardcodes any connection string or credential -- DATABASE_URL is
read from the environment only, exactly like the cloud runner itself.
"""

import os
import sqlite3
import sys

from data_engine import db_backend
from data_engine.paths import DB_PATH

# Every table this migrates -- must stay exactly in sync with
# data_engine/db_backend.py's POSTGRES_SCHEMA. Listed in dependency order
# (a table with no foreign keys to any other table in this set can go in
# any order; none of the 19 curated tables reference each other via
# FOREIGN KEY, so plain insertion order is fine here).
#
# auth_credentials/auth_sessions are listed here for that exact-parity
# guarantee, but this script never actually copies rows into them: on the
# local laptop, login credentials/sessions live in JSON files (sindhu_web/
# auth.py), never in a local SQLite table -- there is no source data for
# migrate_table() to read. It handles that the same as any other table
# absent from the source database (see test_table_absent_from_local_
# database_is_skipped_not_fatal): prints "skipped", copies 0 rows, and
# moves on. A brand-new cloud deploy simply starts with no account set up
# yet, exactly like a first-ever local run -- the CEO creates fresh cloud
# credentials once, and Part 1's Postgres-backed storage keeps them from
# then on.
CURATED_TABLES = [
    "paper_positions",
    "paper_account_state",
    "paper_strategy_config",
    "paper_alerts",
    "confluence_score_log",
    "paper_auto_avoid_rules",
    # paper_coin_blacklist: Grand Feature Expansion, Phase 5 Feature 1 --
    # a small, CEO-curated deny-list, same "worth actually carrying over
    # to a fresh cloud deploy" reasoning as paper_auto_avoid_rules above.
    "paper_coin_blacklist",
    # Master Task 3, Phase 2.9: real, CEO-configured challenges -- worth
    # carrying over to a fresh cloud deploy, same reasoning as
    # paper_coin_blacklist above.
    "challenges",
    "paper_strategy_overrides",
    "paper_lesson_candidates",
    "paper_auto_lessons",
    "paper_decision_log",
    "paper_strategy_stat_archives",
    "telegram_message_log",
    "lessons",
    "paper_strategy_performance",
    "paper_lesson_performance",
    "bot_strategies",
    "bot_lessons",
    "auth_credentials",
    "auth_sessions",
    # cloud_settings: same story as auth_credentials/auth_sessions above --
    # listed for exact-parity with db_backend.POSTGRES_SCHEMA, but never
    # actually migrated. paper_trading_settings.json/telegram_settings.json
    # live as local JSON files, not a SQLite table, on the laptop.
    "cloud_settings",
    # kill_switch_state: same parity-only story -- the local laptop has no
    # need to migrate its (almost always empty) kill switch state.
    "kill_switch_state",
    # activity_log / audit_trail_log: same parity-only story -- these are
    # live logs that start fresh wherever they run, never migrated from
    # the laptop's own history.
    "activity_log",
    "audit_trail_log",
    "telegram_retry_queue",
    # challenge_achievability_snapshots: same parity-only story -- a
    # rolling analytics log, never migrated from the laptop's own history.
    "challenge_achievability_snapshots",
]


def _sqlite_columns(sqlite_conn, table):
    rows = sqlite_conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [r[1] for r in rows]  # r = (cid, name, type, notnull, dflt_value, pk)


def _postgres_columns(pg_cur, table):
    pg_cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s "
        "ORDER BY ordinal_position",
        (table,),
    )
    return [r[0] for r in pg_cur.fetchall()]


def _primary_key_columns(pg_cur, table):
    pg_cur.execute(
        """SELECT a.attname FROM pg_index i
           JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
           WHERE i.indrelid = %s::regclass AND i.indisprimary""",
        (table,),
    )
    return [r[0] for r in pg_cur.fetchall()]


def migrate_table(sqlite_conn, pg_conn, table):
    if table not in [r[0] for r in sqlite_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchall()]:
        print(f"  {table}: not present in the local database (nothing to copy) -- skipped")
        return 0

    pg_cur = pg_conn.cursor()
    sqlite_cols = set(_sqlite_columns(sqlite_conn, table))
    pg_cols_ordered = _postgres_columns(pg_cur, table)
    # Only columns that exist on BOTH sides -- the curated Postgres schema
    # was authored from the SAME live database's PRAGMA table_info, so in
    # practice this is every Postgres column; the intersection is a safety
    # net against schema drift, not the expected common case.
    cols = [c for c in pg_cols_ordered if c in sqlite_cols]
    missing = set(pg_cols_ordered) - sqlite_cols
    if missing:
        print(f"  {table}: local database is missing column(s) {sorted(missing)} -- "
              f"leaving those NULL/default on the Postgres side for every migrated row")

    rows = sqlite_conn.execute(f"SELECT {', '.join(cols)} FROM {table}").fetchall()
    if not rows:
        print(f"  {table}: 0 rows")
        return 0

    pk_cols = _primary_key_columns(pg_cur, table)
    conflict_clause = f"ON CONFLICT ({', '.join(pk_cols)}) DO NOTHING" if pk_cols else "ON CONFLICT DO NOTHING"
    placeholders = ", ".join(["%s"] * len(cols))
    insert_sql = (
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders}) {conflict_clause}"
    )
    pg_cur.executemany(insert_sql, rows)
    print(f"  {table}: {len(rows)} row(s) read from SQLite, {pg_cur.rowcount if pg_cur.rowcount >= 0 else '?'} newly inserted")
    return len(rows)


def main():
    if "DATABASE_URL" not in os.environ:
        print("DATABASE_URL is not set. Set it to the Railway Postgres connection string "
              "(the PUBLIC one, reachable from this laptop) and re-run:\n\n"
              '  DATABASE_URL="postgresql://..." python scripts/migrate_to_postgres.py\n')
        sys.exit(1)

    if not os.path.exists(DB_PATH):
        print(f"No local database found at {DB_PATH} -- nothing to migrate.")
        sys.exit(1)

    print(f"Source (read-only): {DB_PATH}")
    print("Destination: the Postgres database at $DATABASE_URL\n")

    # Read-only: opened directly rather than via data_engine.storage.
    # get_conn(), which would run SQLite's own _migrate_* schema upgrades
    # against the real database as a side effect of connecting.
    sqlite_conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)

    import psycopg2
    pg_conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        db_backend.init_postgres_schema(db_backend._PGConnection(pg_conn))
        pg_conn.commit()

        print("Copying curated tables (paper trading + Telegram only -- "
              "no klines, no backtest history, no AI extraction data):")
        total = 0
        for table in CURATED_TABLES:
            total += migrate_table(sqlite_conn, pg_conn, table)
        pg_conn.commit()
        print(f"\nDone. {total} row(s) read from the local database across "
              f"{len(CURATED_TABLES)} tables. Safe to re-run at any time -- "
              f"rows already present in Postgres are never duplicated or overwritten.")
    except Exception:
        pg_conn.rollback()
        raise
    finally:
        sqlite_conn.close()
        pg_conn.close()


if __name__ == "__main__":
    main()
