"""Weekly Auto-Snapshot (Grand Feature Expansion, Phase 7 Feature 3): a
genuinely WEEKLY-cadence database snapshot, distinct from
sindhu_web.api.backup's existing rolling 6-hourly backup -- that backup's
own retention (_prune_old_backups, keep_last=10) has no week-boundary
awareness at all, so a full week of history is never actually guaranteed
to survive it (10 backups at the default 6-hour interval is only ~2.5
days). Weekly snapshots live in their own folder with their own,
longer retention (keep_last=8, ~2 months of weekly history) so the two
schedules can never interfere with or prune each other.

Reuses backup._hot_copy() for the actual copy mechanism -- the SAME
sqlite3 backup API, just a different destination and retention policy."""

import os
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter

from data_engine.paths import DATABASE_DIR
from data_engine.logging_setup import log
from sindhu_web import sync
from sindhu_web.api.backup import _hot_copy, _now_stamp

router = APIRouter()

_SNAPSHOT_DIR = os.path.join(DATABASE_DIR, "weekly_snapshots")
SNAPSHOT_INTERVAL_DAYS = 7
KEEP_LAST = 8


def create_weekly_snapshot():
    os.makedirs(_SNAPSHOT_DIR, exist_ok=True)
    snapshot_name = f"sindhu_weekly_{_now_stamp()}.db"
    snapshot_path = os.path.join(_SNAPSHOT_DIR, snapshot_name)
    _hot_copy(snapshot_path)
    log(f"Weekly snapshot created: {snapshot_name}")
    sync.notify("weekly_snapshot", "created", f"Weekly database snapshot created: {snapshot_name}")
    _prune_old_snapshots()
    return snapshot_name


def _prune_old_snapshots():
    if not os.path.isdir(_SNAPSHOT_DIR):
        return
    files = sorted(
        (f for f in os.listdir(_SNAPSHOT_DIR) if f.startswith("sindhu_weekly_") and f.endswith(".db")),
        reverse=True,  # newest first (filenames are timestamp-sortable)
    )
    for stale in files[KEEP_LAST:]:
        try:
            os.remove(os.path.join(_SNAPSHOT_DIR, stale))
            log(f"Pruned old weekly snapshot: {stale}")
        except OSError as e:
            log(f"Failed to prune old weekly snapshot {stale}: {e!r}")


def list_weekly_snapshots():
    if not os.path.isdir(_SNAPSHOT_DIR):
        return []
    items = []
    for f in sorted(os.listdir(_SNAPSHOT_DIR), reverse=True):
        path = os.path.join(_SNAPSHOT_DIR, f)
        items.append({
            "name": f, "size_bytes": os.path.getsize(path),
            "modified_at": datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc).isoformat(),
        })
    return items


def _latest_snapshot_time():
    snapshots = list_weekly_snapshots()
    return snapshots[0]["modified_at"] if snapshots else None


def maybe_create_weekly_snapshot():
    """Called periodically by the scheduler thread -- only actually
    snapshots if 7+ days have passed since the last one (or none exists
    yet). Safe to call as often as convenient."""
    last = _latest_snapshot_time()
    if last:
        last_dt = datetime.fromisoformat(last)
        if datetime.now(timezone.utc) - last_dt < timedelta(days=SNAPSHOT_INTERVAL_DAYS):
            return None
    return create_weekly_snapshot()


def start_weekly_snapshot_scheduler_thread():
    """Runs once at server startup; checks every few hours whether a new
    snapshot is due -- same shape as sindhu_web.api.backup's own
    start_auto_backup_thread and paper_trading.weekly_report's scheduler."""
    import threading
    import time

    def _loop():
        while True:
            try:
                result = maybe_create_weekly_snapshot()
                if result:
                    log(f"[weekly-snapshot] created {result}")
            except Exception as e:
                log(f"[weekly-snapshot] failed: {e!r}")
            time.sleep(6 * 3600)  # check every 6 hours; the 7-day gate above prevents over-snapshotting

    threading.Thread(target=_loop, daemon=True).start()


@router.get("/api/weekly-snapshot/list")
def get_weekly_snapshots():
    return {"snapshots": list_weekly_snapshots()}


@router.post("/api/weekly-snapshot/create-now")
def create_weekly_snapshot_now():
    """Manual trigger, bypassing the 7-day gate -- for testing/on-demand use."""
    name = create_weekly_snapshot()
    return {"snapshot": name}
