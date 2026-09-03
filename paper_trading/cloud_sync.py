"""Cloud-to-local data sync (this task, Part 6): a scheduled, ONE-WAY
backup of the lightweight cloud runner's own Paper Trading + Telegram
data, so it isn't solely dependent on the cloud database surviving
indefinitely. Runs automatically once every 24 hours (see
start_cloud_sync_scheduler_thread(), started from cloud_runtime/app.py's
lifespan only -- never from the local laptop's full app) and is always
downloadable on demand via the authenticated
GET /api/paper-trading/cloud-sync/download endpoint.

Deliberately one-way and lightweight, per this task's own requirement:
- Only the curated paper-trading/Telegram data this cloud runner actually
  owns (open positions, closed trades, the Telegram signal log, and
  per-strategy performance stats) -- never klines/historical candle data,
  which this runner's own Postgres schema doesn't even store (see
  data_engine/db_backend.py's POSTGRES_SCHEMA docstring).
- Nothing here ever WRITES data back into the cloud database from the
  local laptop -- this module only ever reads the cloud's own data and
  hands it out for download. The local laptop pulling this file down is
  the CEO's own separate action; nothing here reaches out to the laptop.

Snapshot storage follows the same cloud_settings convention as
paper_trading/config.py and paper_trading/telegram_bot.py: Postgres when
DATABASE_URL is connected (so the snapshot survives the same
restarts/redeploys it's protecting against), a local JSON file otherwise
(e.g. a local smoke test with no Postgres server).

Scheduling follows this codebase's own established convention (see
sindhu_strategy/generator.py's _scheduler_loop, paper_trading/
daily_report.py's start_daily_report_scheduler_thread) rather than
introducing a new one: a daemon thread, an hourly check against a
calendar/interval-elapsed gate, never a raw 24h sleep (which wouldn't
notice a delayed process start and could drift).
"""

import json
import os
import threading
from datetime import datetime, timezone

from data_engine import config as base_config, db_backend, storage
from data_engine.logging_setup import log as default_log

_SNAPSHOT_KEY = "cloud_sync_snapshot"
_SNAPSHOT_FILE = "cloud_sync_snapshot.json"
SYNC_INTERVAL_SECONDS = 24 * 3600
_CHECK_INTERVAL_SECONDS = 3600  # hourly gate check -- see module docstring

_stop_flag = threading.Event()
_thread = None


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def build_snapshot():
    """Gathers exactly the lightweight data this cloud runner owns. Every
    field reuses an existing storage/telegram_analytics function -- no new
    query logic, so this can never drift from what those already track."""
    return {
        "generated_at": _now_iso(),
        "open_positions": storage.get_open_paper_positions(),
        # A large limit, not a new "no limit" code path in storage.py --
        # a backup should include real history, not just a recent slice.
        "closed_positions": storage.list_closed_paper_positions(limit=1_000_000),
        "telegram_signal_log": storage.list_telegram_signal_outcomes(),
        "strategy_performance": storage.list_paper_strategy_performance(),
        "strategy_stats": storage.list_paper_strategy_stats(),
    }


def run_sync():
    """Builds a fresh snapshot and persists it. Returns the snapshot."""
    snapshot = build_snapshot()
    if db_backend.IS_POSTGRES:
        storage.save_cloud_setting(_SNAPSHOT_KEY, snapshot, snapshot["generated_at"])
    else:
        base_config.save_config(_SNAPSHOT_FILE, snapshot)
    return snapshot


def get_latest_snapshot():
    """None if the scheduled job has never run yet (a brand-new deploy) --
    never a fabricated/empty-looking snapshot that could be mistaken for
    "genuinely synced, zero data.\""""
    if db_backend.IS_POSTGRES:
        return storage.get_cloud_setting(_SNAPSHOT_KEY)
    path = os.path.join(base_config.CONFIG_DIR, _SNAPSHOT_FILE)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _should_run_now():
    latest = get_latest_snapshot()
    if not latest:
        return True
    last_generated = datetime.fromisoformat(latest["generated_at"])
    return (datetime.now(timezone.utc) - last_generated).total_seconds() >= SYNC_INTERVAL_SECONDS


def _loop():
    default_log("[cloud-sync] scheduler started -- checks hourly, syncs at most once per 24h.")
    while not _stop_flag.is_set():
        try:
            if _should_run_now():
                snapshot = run_sync()
                default_log(f"[cloud-sync] snapshot generated at {snapshot['generated_at']} "
                            f"({len(snapshot['open_positions'])} open, "
                            f"{len(snapshot['closed_positions'])} closed positions).")
        except Exception as e:
            default_log(f"[cloud-sync] snapshot failed: {e!r}")
        _stop_flag.wait(_CHECK_INTERVAL_SECONDS)


def start_cloud_sync_scheduler_thread():
    """Call once from cloud_runtime/app.py's lifespan -- never from the
    local laptop's full app (sindhu_web/server.py), per this task's own
    scope rule (cloud_runtime and related cloud-deployment code only)."""
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop_flag.clear()
    _thread = threading.Thread(target=_loop, daemon=True)
    _thread.start()


def stop_cloud_sync_scheduler_thread():
    """Test/shutdown hook -- mirrors the stop-flag pattern already used by
    paper_trading.engine's own _stop_flag."""
    _stop_flag.set()
