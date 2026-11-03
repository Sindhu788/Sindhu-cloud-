"""Database size awareness (read-only measurement + bounded pruning of append-only logs).

Why: the Cloud database is a small hosted Postgres. The big market-data tables
(klines_1m, backtest_*, ai_*) are deliberately NOT part of the Postgres schema,
but append-only logs can still fill a small database over time. This module
measures usage, logs a clear WARNING before it is full, and prunes ONLY the
scan-receipt log (a diagnostics table, never trades/signals/settings/strategies).

Environment variable names (values are not secrets):
  SINDHU_DB_SIZE_LIMIT_MB          capacity to compare against (default 500 on Postgres; unset = no % warning on SQLite)
  SINDHU_DB_WARN_PCT               warn at this usage percentage (default 80)
  SINDHU_SCAN_LOG_RETENTION_DAYS   keep this many days of paper_scan_log (default 7)
  SINDHU_SCAN_LOG_MAX_ROWS         hard row cap for paper_scan_log (default 20000)
"""
import os
from datetime import datetime, timedelta, timezone

from data_engine import db_backend

_PRUNABLE = {"paper_scan_log": "completed_at"}


def _int_env(name, default):
    try:
        return int(float(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


def database_usage(top_n=5):
    """Returns {backend,size_bytes,limit_bytes,pct,top_tables:[(name,bytes)],error}. Never raises."""
    out = {"backend": "postgres" if db_backend.IS_POSTGRES else "sqlite", "size_bytes": None,
           "limit_bytes": None, "pct": None, "top_tables": [], "error": None}
    limit_mb = os.environ.get("SINDHU_DB_SIZE_LIMIT_MB")
    if limit_mb is None and db_backend.IS_POSTGRES:
        limit_mb = "500"
    if limit_mb:
        try:
            out["limit_bytes"] = int(float(limit_mb) * 1024 * 1024)
        except ValueError:
            pass
    try:
        from data_engine import storage
        if db_backend.IS_POSTGRES:
            with storage.get_conn() as c:
                out["size_bytes"] = int(c.execute("SELECT pg_database_size(current_database())").fetchone()[0])
                rows = c.execute(
                    "SELECT relname, pg_total_relation_size(c.oid) FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE c.relkind = 'r' AND n.nspname = 'public' ORDER BY 2 DESC LIMIT ?", (top_n,)).fetchall()
                out["top_tables"] = [(r[0], int(r[1])) for r in rows]
        else:
            out["size_bytes"] = os.path.getsize(storage.DB_PATH) if os.path.exists(storage.DB_PATH) else 0
    except Exception as exc:  # measurement must never break a caller
        out["error"] = type(exc).__name__
    if out["size_bytes"] is not None and out["limit_bytes"]:
        out["pct"] = round(100.0 * out["size_bytes"] / out["limit_bytes"], 1)
    return out


def check_and_warn(log=None):
    """Log a WARNING when usage is at/above SINDHU_DB_WARN_PCT. Returns the usage dict."""
    if log is None:
        from data_engine.logging_setup import log as _l
        log = _l
    usage = database_usage()
    warn_pct = _int_env("SINDHU_DB_WARN_PCT", 80)
    if usage["pct"] is not None and usage["pct"] >= warn_pct:
        top = ", ".join(f"{n} {b // (1024 * 1024)}MB" for n, b in usage["top_tables"][:3]) or "n/a"
        log(f"[db-size] WARNING database is {usage['pct']}% full "
            f"({usage['size_bytes'] // (1024 * 1024)}MB of {usage['limit_bytes'] // (1024 * 1024)}MB). "
            f"Biggest tables: {top}. Writes will start failing at 100% -- free space or raise the plan.")
    return usage


def prune_append_only_logs(now=None):
    """Delete old rows from the scan-receipt log only. Returns {table: rows_deleted}."""
    from data_engine import storage
    days = _int_env("SINDHU_SCAN_LOG_RETENTION_DAYS", 7)
    max_rows = _int_env("SINDHU_SCAN_LOG_MAX_ROWS", 20000)
    cutoff = ((now or datetime.now(timezone.utc)) - timedelta(days=days)).isoformat()
    deleted = {}
    try:
        with storage.get_conn() as conn:
            for table, ts_col in _PRUNABLE.items():
                try:
                    before = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                except Exception:
                    continue  # table not created yet (scanner never ran)
                conn.execute(f"DELETE FROM {table} WHERE {ts_col} < ?", (cutoff,))
                conn.execute(
                    f"DELETE FROM {table} WHERE id NOT IN (SELECT id FROM {table} ORDER BY {ts_col} DESC LIMIT ?)",
                    (max_rows,))
                after = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                deleted[table] = before - after
    except Exception:
        pass
    return deleted
