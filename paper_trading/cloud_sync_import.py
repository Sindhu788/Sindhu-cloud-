"""Cloud-to-local import: completes paper_trading/cloud_sync.py's
previously one-way backup (cloud generates a snapshot -> CEO downloads it
via GET /api/paper-trading/cloud-sync/download -- and, until now, nothing
ever brought that JSON back into the local database).

Deliberately narrow, matching cloud_sync.py's own one-way design note
("this module only ever reads the cloud's own data") -- the goal here is
a SAFE MERGE of trade history, never a full state mirror:

- Only CLOSED positions are merged into paper_positions. These are
  finished, append-only historical records that can never conflict with
  whatever the local engine's own book is currently doing. Deduplicated
  by id (paper_positions.id is a uuid4 hex -- see paper_trading/
  position_manager.py -- so "id already exists locally" reliably means
  "already imported", never a false-positive skip) via
  storage.import_closed_paper_position()'s own ON CONFLICT DO NOTHING.

- OPEN positions in the snapshot are deliberately NOT merged into the
  local paper_positions table: they are the cloud engine's live,
  still-changing book at the moment the snapshot was taken, and the local
  engine has no SL/TP monitoring loop for a position it never opened.
  They will be imported automatically on a LATER run, once the cloud
  closes them and a future snapshot reports them under closed_positions
  instead -- nothing is permanently lost by skipping them now.

- telegram_signal_log/strategy_performance/strategy_stats in the snapshot
  are computed/joined views (see storage.list_telegram_signal_outcomes,
  list_paper_strategy_performance, list_paper_strategy_stats), not raw
  insertable table rows -- reconstructing telegram_message_log rows from
  the joined shape would require guessing fields the join doesn't carry
  (trigger_type, success, chat_id). Skipped rather than writing a lossy,
  partially-fabricated history.

Only ever meant to run on the local laptop (IS_POSTGRES is False there);
running it against the cloud runner's own database would be importing the
cloud's data into itself, which is refused outright.
"""
from datetime import datetime, timezone

from data_engine import db_backend, storage

_AUDIT_ENTITY = "cloud_sync_import"


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def import_snapshot(snapshot):
    """Merges one cloud_sync.py snapshot dict into the local database.
    Always returns a summary dict describing exactly what happened --
    never silently drops data without saying so."""
    if db_backend.IS_POSTGRES:
        return {"ok": False, "error": "import only runs on the local machine, not the cloud deployment"}

    if not isinstance(snapshot, dict) or "closed_positions" not in snapshot:
        return {"ok": False, "error": "not a recognized cloud-sync snapshot (missing 'closed_positions')"}

    closed = snapshot.get("closed_positions") or []
    imported = 0
    duplicates = 0
    failed = 0
    for pos in closed:
        try:
            if storage.import_closed_paper_position(pos):
                imported += 1
            else:
                duplicates += 1
        except Exception:
            failed += 1

    open_count = len(snapshot.get("open_positions") or [])
    now = _now_iso()
    storage.record_audit_event(
        _AUDIT_ENTITY, "success",
        f"imported {imported} closed trade(s) from a cloud backup generated "
        f"{snapshot.get('generated_at', 'an unknown time')} "
        f"({duplicates} already present, {failed} failed, {open_count} open position(s) skipped -- "
        f"still live on the cloud)",
        now,
    )
    return {
        "ok": True,
        "closed_positions_imported": imported,
        "closed_positions_already_present": duplicates,
        "closed_positions_failed": failed,
        "open_positions_skipped": open_count,
        "snapshot_generated_at": snapshot.get("generated_at"),
    }
