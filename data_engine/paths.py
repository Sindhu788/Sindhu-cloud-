"""Central folder structure for SINDHU.

Everything the app persists lives under data/, split into purpose-specific
subfolders so the project stays organized as it grows in later phases.
"""

import os
import shutil

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

DATABASE_DIR = os.path.join(DATA_DIR, "database")
MARKET_DATA_DIR = os.path.join(DATA_DIR, "market_data")
LOGS_DIR = os.path.join(DATA_DIR, "logs")
REPORTS_DIR = os.path.join(DATA_DIR, "reports")
SETTINGS_DIR = os.path.join(DATA_DIR, "settings")
HISTORY_DIR = os.path.join(DATA_DIR, "history")
CONFIG_DIR = os.path.join(DATA_DIR, "config")

ALL_DIRS = [
    DATABASE_DIR, MARKET_DATA_DIR, LOGS_DIR, REPORTS_DIR,
    SETTINGS_DIR, HISTORY_DIR, CONFIG_DIR,
]

DB_PATH = os.path.join(DATABASE_DIR, "sindhu.db")
LOG_FILE = os.path.join(LOGS_DIR, "sindhu.log")
SESSION_FILE = os.path.join(HISTORY_DIR, "sessions.jsonl")


def ensure_folders():
    os.makedirs(DATA_DIR, exist_ok=True)
    for d in ALL_DIRS:
        os.makedirs(d, exist_ok=True)


def migrate_legacy_files():
    """Move files from the old flat data/ layout into the new subfolders.
    Safe to call every startup: only moves a legacy file if it exists and
    nothing has already been placed at the new destination."""
    ensure_folders()

    legacy_db = os.path.join(DATA_DIR, "sindhu.db")
    if os.path.exists(legacy_db) and not os.path.exists(DB_PATH):
        shutil.move(legacy_db, DB_PATH)
    for suffix in ("-wal", "-shm"):
        legacy_side = legacy_db + suffix
        new_side = DB_PATH + suffix
        if os.path.exists(legacy_side) and not os.path.exists(new_side):
            shutil.move(legacy_side, new_side)

    legacy_log = os.path.join(DATA_DIR, "download_console.log")
    new_log_dest = os.path.join(LOGS_DIR, "download_console.log")
    if os.path.exists(legacy_log) and not os.path.exists(new_log_dest):
        shutil.move(legacy_log, new_log_dest)


def disk_usage_bytes():
    """Total bytes used by everything under data/."""
    total = 0
    for root, _dirs, files in os.walk(DATA_DIR):
        for f in files:
            fp = os.path.join(root, f)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total
