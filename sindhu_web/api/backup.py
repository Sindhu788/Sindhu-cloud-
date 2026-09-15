import gzip
import json
import os
import sqlite3
import tempfile
import threading
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from data_engine import config, db_backend, feature_toggles, storage
from data_engine.paths import DATABASE_DIR, DB_PATH
from data_engine.logging_setup import log
from sindhu_web import sync

router = APIRouter()

_BACKUP_DIR = os.path.join(DATABASE_DIR, "backups")
# Automated Backup Engine (System Reliability Group, item 8): runs
# continuously and unattended, separate from the one-off manual archive
# snapshot done earlier in the project. Every few hours is frequent enough
# to bound data loss without generating excessive backup file churn for a
# single-machine personal deployment; keep_last=10 bounds disk usage while
# still covering roughly 1-2 days of history at the default interval.
_DEFAULT_BACKUP_SETTINGS = {"auto_backup_enabled": True, "interval_hours": 6, "keep_last": 10}

_DRILL_STATUS_PATH = os.path.join(DATABASE_DIR, "backup_drill_status.json")

# 2026-09-15, Grand Master Batch #2, Phase 1.5: found live -- everything in
# this file used raw sqlite3.connect(DB_PATH) unconditionally, with no
# db_backend.IS_POSTGRES branch anywhere. On the live Render cloud service
# (DATABASE_URL set -> Postgres is the REAL database, see
# data_engine/db_backend.py), DB_PATH still points at a local SQLite file
# that the app never writes trading data to -- so the "automated backup"
# there was silently backing up an empty/stale file, not production data,
# every 6 hours, and would have reported success the whole time. Fixed by
# giving Postgres its own logical-dump backup path below; the local laptop
# (SQLite, DATABASE_URL unset) is completely unaffected -- same file names,
# same _hot_copy, same behavior as before this fix.
# A small subset of tables (curated in db_backend.POSTGRES_SCHEMA) is all
# that exists on the cloud runner in the first place -- see that module's
# own docstring for why the huge klines_1m/backtest_*/ai_* tables are
# intentionally not part of it.
_CORE_TABLE_CHECK_LIST = [
    "paper_positions", "telegram_message_log", "bot_strategies", "lessons",
    "kill_switch_state", "account_drawdown_state", "challenges",
]


def _now_stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _hot_copy(src_path, dest_path):
    """Safe hot-copy of a SQLite database via sqlite3's own backup API --
    correct even while the desktop app / web server has it open, unlike a
    raw file copy which could grab a half-written page. Shared by
    create_backup() (the rolling 6-hourly backup), weekly_snapshot's own
    snapshot feature, restore_backup(), and _sqlite_restore_drill() below --
    the actual copy mechanism is identical, only source/destination and
    what happens afterward differ."""
    src = sqlite3.connect(src_path)
    dst = sqlite3.connect(dest_path)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()


# --------------------------------------------------------------- Postgres logical backup

def _postgres_table_names(conn):
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name"
    ).fetchall()
    return [r[0] for r in rows]


def dump_postgres_tables(conn):
    """Reads every real table's full contents through the SAME connection
    wrapper storage.py's own 5000+ lines of queries already use (never a
    second, unaudited DB access path) and returns {table: {"columns":[...],
    "rows":[[...], ...]}}. Split out from _create_postgres_backup() so
    tests can exercise it against a lightweight fake connection without a
    real Postgres server."""
    dump = {}
    for table in _postgres_table_names(conn):
        cur = conn.execute(f"SELECT * FROM {table}")
        columns = [d[0] for d in cur.description]
        rows = [list(r) for r in cur.fetchall()]
        dump[table] = {"columns": columns, "rows": rows}
    return dump


def _create_postgres_backup(dest_path):
    with storage.get_conn() as conn:
        dump = dump_postgres_tables(conn)
    with gzip.open(dest_path, "wt", encoding="utf-8") as f:
        json.dump(dump, f, default=str)
    return dump


def create_backup():
    os.makedirs(_BACKUP_DIR, exist_ok=True)
    if db_backend.IS_POSTGRES:
        backup_name = f"sindhu_pg_{_now_stamp()}.json.gz"
        backup_path = os.path.join(_BACKUP_DIR, backup_name)
        _create_postgres_backup(backup_path)
    else:
        backup_name = f"sindhu_{_now_stamp()}.db"
        backup_path = os.path.join(_BACKUP_DIR, backup_name)
        _hot_copy(DB_PATH, backup_path)
    log(f"Backup created: {backup_name}")
    sync.notify("backup", "created", f"Database backup created: {backup_name}")
    _prune_old_backups()
    return backup_name


def _is_backup_file(name):
    return (name.startswith("sindhu_") and name.endswith(".db")) or (name.startswith("sindhu_pg_") and name.endswith(".json.gz"))


def _prune_old_backups():
    """Keeps only the most recent `keep_last` backups, oldest deleted first.
    Called after every create_backup() (both manual and automatic) so the
    limit holds regardless of which path created the newest one. Covers
    both backup file shapes (SQLite .db and Postgres .json.gz) in one
    timestamp-sortable list."""
    settings = config.load_or_seed("backup_settings.json", _DEFAULT_BACKUP_SETTINGS)
    keep_last = settings.get("keep_last", 10)
    if not os.path.isdir(_BACKUP_DIR):
        return
    files = sorted(
        (f for f in os.listdir(_BACKUP_DIR) if _is_backup_file(f)),
        reverse=True,  # newest first (filenames are timestamp-sortable)
    )
    for stale in files[keep_last:]:
        try:
            os.remove(os.path.join(_BACKUP_DIR, stale))
            log(f"Pruned old backup: {stale}")
        except OSError as e:
            log(f"Failed to prune old backup {stale}: {e!r}")


@router.post("/api/backup/create")
def manual_backup():
    name = create_backup()
    return {"backup": name}


@router.get("/api/backup/list")
def list_backups():
    if not os.path.isdir(_BACKUP_DIR):
        return {"backups": []}
    items = []
    for f in sorted(os.listdir(_BACKUP_DIR), reverse=True):
        if not _is_backup_file(f):
            continue
        path = os.path.join(_BACKUP_DIR, f)
        items.append({
            "name": f, "size_bytes": os.path.getsize(path),
            "modified_at": datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc).isoformat(),
            "backend": "postgres" if f.endswith(".json.gz") else "sqlite",
        })
    return {"backups": items}


class RestoreRequest(BaseModel):
    backup_name: str
    confirm: bool = False


@router.post("/api/backup/restore")
def restore_backup(req: RestoreRequest):
    if not req.confirm:
        raise HTTPException(400, "set confirm=true to proceed -- this overwrites the live database")
    backup_path = os.path.join(_BACKUP_DIR, req.backup_name)
    if not os.path.isfile(backup_path):
        raise HTTPException(404, "backup not found")

    if req.backup_name.endswith(".json.gz"):
        # 2026-09-15: deliberately NOT automated. Replaying a Postgres
        # logical dump back into the live production database is a
        # permanently-irreversible write to real trading data (open
        # positions, balances, kill-switch state) -- exactly the class of
        # action the project's standing safety rules require a human to
        # perform deliberately, not something to script into a one-click
        # API call. The dump file itself is real and verified (see
        # verify_backup() below) and can be inspected/replayed manually.
        raise HTTPException(
            501,
            "Postgres restore is not automated for safety -- this would overwrite live production data. "
            "Download the .json.gz dump and restore it manually with deliberate review, "
            "or ask for this to be done by hand.",
        )

    create_backup()  # safety snapshot of current state before restoring
    _hot_copy(backup_path, DB_PATH)
    log(f"Database restored from backup: {req.backup_name}")
    sync.notify("backup", "restored", f"Database restored from backup: {req.backup_name}")
    return {"ok": True}


# --------------------------------------------------------------- Restore-verification drill
# Phase 1.5: "a backup is only reported successful if a real restore test
# confirms the file is usable." Runs the ACTUAL restore mechanism against a
# throwaway scratch destination (never the live database), then queries the
# result -- not just "the file exists and has a plausible size."

def _sqlite_restore_drill(backup_path):
    with tempfile.TemporaryDirectory(prefix="sindhu_restore_drill_") as tmp_dir:
        scratch_path = os.path.join(tmp_dir, "restored_scratch.db")
        _hot_copy(backup_path, scratch_path)  # exercises the real restore code path, throwaway destination
        conn = sqlite3.connect(scratch_path)
        try:
            quick_check = conn.execute("PRAGMA quick_check;").fetchone()[0]
            if quick_check != "ok":
                return {"ok": False, "error": f"PRAGMA quick_check failed: {quick_check}", "checked_tables": {}}
            present_tables = {
                r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            checked = {}
            for t in _CORE_TABLE_CHECK_LIST:
                if t in present_tables:
                    checked[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            return {"ok": True, "error": None, "checked_tables": checked}
        finally:
            conn.close()


def _postgres_restore_drill(backup_path):
    """Reconstructs the dump into a throwaway in-memory-equivalent SQLite
    scratch database (never touches live Postgres) -- proves the archive is
    genuinely un-corrupted and every table's rows can be fully replayed,
    not just that gzip/json parsed without an exception."""
    with gzip.open(backup_path, "rt", encoding="utf-8") as f:
        dump = json.load(f)
    if not dump:
        return {"ok": False, "error": "backup contains zero tables", "checked_tables": {}}

    with tempfile.TemporaryDirectory(prefix="sindhu_restore_drill_") as tmp_dir:
        scratch_path = os.path.join(tmp_dir, "restored_scratch.db")
        conn = sqlite3.connect(scratch_path)
        try:
            checked = {}
            for table, payload in dump.items():
                columns = payload["columns"]
                rows = payload["rows"]
                if not columns:
                    continue
                col_list = ", ".join(f'"{c}"' for c in columns)
                placeholders = ", ".join("?" for _ in columns)
                conn.execute(f'CREATE TABLE "{table}" ({col_list})')
                if rows:
                    conn.executemany(f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders})', rows)
                conn.commit()
                restored_count = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                if restored_count != len(rows):
                    return {
                        "ok": False,
                        "error": f"table {table}: dump had {len(rows)} rows but only {restored_count} replayed",
                        "checked_tables": checked,
                    }
                if table in _CORE_TABLE_CHECK_LIST:
                    checked[table] = restored_count
            return {"ok": True, "error": None, "checked_tables": checked}
        finally:
            conn.close()


def verify_backup(backup_name):
    """Runs the real restore drill for whichever backend produced this
    backup file and returns {"ok", "backend", "backup_name", "error",
    "checked_tables", "verified_at"}. Never writes to the live database --
    every restore happens against a throwaway scratch file that is deleted
    immediately after."""
    backup_path = os.path.join(_BACKUP_DIR, backup_name)
    if not os.path.isfile(backup_path):
        return {"ok": False, "backend": None, "backup_name": backup_name, "error": "backup not found", "checked_tables": {}}

    try:
        if backup_name.endswith(".json.gz"):
            result = _postgres_restore_drill(backup_path)
            backend = "postgres"
        else:
            result = _sqlite_restore_drill(backup_path)
            backend = "sqlite"
    except Exception as e:
        result = {"ok": False, "error": repr(e), "checked_tables": {}}
        backend = "postgres" if backup_name.endswith(".json.gz") else "sqlite"

    return {
        "ok": result["ok"], "backend": backend, "backup_name": backup_name,
        "error": result["error"], "checked_tables": result["checked_tables"],
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }


def _save_drill_status(result):
    try:
        os.makedirs(DATABASE_DIR, exist_ok=True)
        with open(_DRILL_STATUS_PATH, "w", encoding="utf-8") as f:
            json.dump(result, f)
    except OSError as e:
        log(f"Failed to save backup drill status: {e!r}")


def latest_drill_status():
    """Read by the Operational Health / Control Center screen (Phase 4.3 /
    5.1) so a silently-broken backup pipeline shows up as a visible status
    instead of nobody ever finding out until a real restore is needed."""
    if not os.path.isfile(_DRILL_STATUS_PATH):
        return {"ok": None, "error": "no restore drill has run yet"}
    try:
        with open(_DRILL_STATUS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return {"ok": None, "error": f"could not read drill status: {e!r}"}


@router.post("/api/backup/verify")
def verify_latest_backup():
    """Manual trigger: verifies the MOST RECENT backup right now and
    persists the result, same as the automatic daily drill does."""
    if not os.path.isdir(_BACKUP_DIR):
        raise HTTPException(404, "no backups exist yet")
    files = sorted((f for f in os.listdir(_BACKUP_DIR) if _is_backup_file(f)), reverse=True)
    if not files:
        raise HTTPException(404, "no backups exist yet")
    result = verify_backup(files[0])
    _save_drill_status(result)
    if not result["ok"]:
        log(f"Backup restore drill FAILED for {files[0]}: {result['error']}")
        sync.notify("backup", "drill_failed", f"Restore drill failed for {files[0]}: {result['error']}")
    return result


@router.get("/api/backup/drill-status")
def get_drill_status():
    return latest_drill_status()


def start_auto_backup_thread():
    """Runs once at server startup; sleeps between backups so it never
    competes with foreground DB activity. The thread itself always starts
    -- whether a backup actually runs each cycle is re-checked fresh every
    time from both backup_settings.json and the Feature Control Center's
    master/per-feature toggles, so flipping either OFF takes effect on the
    very next cycle without needing a server restart."""

    def _loop():
        while True:
            settings = config.load_or_seed("backup_settings.json", _DEFAULT_BACKUP_SETTINGS)
            time.sleep(max(settings["interval_hours"], 1) * 3600)
            if not settings.get("auto_backup_enabled", True) or not feature_toggles.is_enabled("backup_enabled"):
                continue
            try:
                name = create_backup()
                result = verify_backup(name)
                _save_drill_status(result)
                if not result["ok"]:
                    log(f"Backup restore drill FAILED for {name}: {result['error']}")
                    sync.notify("backup", "drill_failed", f"Restore drill failed for {name}: {result['error']}")
            except Exception as e:
                log(f"Automatic backup failed: {e!r}")

    threading.Thread(target=_loop, daemon=True).start()
