import os
import sqlite3
import threading
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from data_engine import config
from data_engine.paths import DATABASE_DIR, DB_PATH
from data_engine.logging_setup import log

router = APIRouter()

_BACKUP_DIR = os.path.join(DATABASE_DIR, "backups")
_DEFAULT_BACKUP_SETTINGS = {"auto_backup_enabled": True, "interval_hours": 24}


def _now_stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def create_backup():
    """Safe hot-copy of the live database via sqlite3's own backup API --
    correct even while the desktop app / web server has it open, unlike a
    raw file copy which could grab a half-written page."""
    os.makedirs(_BACKUP_DIR, exist_ok=True)
    backup_name = f"sindhu_{_now_stamp()}.db"
    backup_path = os.path.join(_BACKUP_DIR, backup_name)

    src = sqlite3.connect(DB_PATH)
    dst = sqlite3.connect(backup_path)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()
    log(f"Backup created: {backup_name}")
    return backup_name


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
        path = os.path.join(_BACKUP_DIR, f)
        items.append({
            "name": f, "size_bytes": os.path.getsize(path),
            "modified_at": datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc).isoformat(),
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

    create_backup()  # safety snapshot of current state before restoring

    src = sqlite3.connect(backup_path)
    dst = sqlite3.connect(DB_PATH)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()
    log(f"Database restored from backup: {req.backup_name}")
    return {"ok": True}


def start_auto_backup_thread():
    """Runs once at server startup; sleeps between backups so it never
    competes with foreground DB activity."""
    settings = config.load_or_seed("backup_settings.json", _DEFAULT_BACKUP_SETTINGS)
    if not settings.get("auto_backup_enabled", True):
        return

    def _loop():
        while True:
            interval = config.load_or_seed("backup_settings.json", _DEFAULT_BACKUP_SETTINGS)["interval_hours"]
            time.sleep(max(interval, 1) * 3600)
            try:
                create_backup()
            except Exception as e:
                log(f"Automatic backup failed: {e!r}")

    threading.Thread(target=_loop, daemon=True).start()
