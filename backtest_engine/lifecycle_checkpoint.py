"""Simple, disk-durable checkpoint helper for large sequential batch jobs
(Strategy Lifecycle Part 0). Each checkpoint file lives under
strategies/lifecycle_checkpoints/<task_id>.json and is rewritten to disk
after EVERY item, not just at the end of a run -- so a power loss or session
restart mid-batch loses at most the one item that was in progress, never
already-completed work.

Write is atomic (write to a .tmp file, then os.replace) so a crash mid-write
can never leave a half-written, corrupt checkpoint file behind.

Usage pattern:
    cp = load(task_id, item_ids=[...])          # creates fresh if none exists
    for item_id in pending(cp):                  # skips done items on resume
        mark_in_progress(cp, item_id); save(task_id, cp)
        result = do_work(item_id)
        mark_done(cp, item_id, result); save(task_id, cp)
"""

import json
import os
from datetime import datetime, timezone

_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "strategies", "lifecycle_checkpoints",
)


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _path(task_id):
    return os.path.join(_DIR, f"{task_id}.json")


def load(task_id, item_ids=None):
    """Loads the existing checkpoint for task_id if one is on disk (resume
    case). Otherwise creates a fresh one seeded with item_ids all 'pending'.
    item_ids is required the first time a task is started; ignored on resume
    (the existing item set on disk wins, so a resume never silently drops
    progress because the caller passed a slightly different list)."""
    p = _path(task_id)
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    if item_ids is None:
        raise ValueError(f"No checkpoint on disk for '{task_id}' and no item_ids given to start one")
    cp = {
        "task_id": task_id,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "items": {iid: {"status": "pending", "result": None} for iid in item_ids},
    }
    save(task_id, cp)
    return cp


def read_only(task_id):
    """Loads a checkpoint for display purposes without creating one if it
    doesn't exist yet (unlike load(), which requires item_ids to start a
    fresh one). Returns None if this task has never been checkpointed."""
    p = _path(task_id)
    if not os.path.exists(p):
        return None
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def save(task_id, cp):
    os.makedirs(_DIR, exist_ok=True)
    cp["updated_at"] = _now_iso()
    p = _path(task_id)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cp, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def mark_in_progress(cp, item_id):
    cp["items"][item_id]["status"] = "in_progress"


def mark_done(cp, item_id, result):
    cp["items"][item_id]["status"] = "done"
    cp["items"][item_id]["result"] = result


def mark_skipped(cp, item_id, reason):
    cp["items"][item_id]["status"] = "skipped"
    cp["items"][item_id]["result"] = {"skipped_reason": reason}


def pending(cp):
    """Item ids still needing work, in their original order."""
    return [iid for iid, v in cp["items"].items() if v["status"] not in ("done", "skipped")]


def summary(cp):
    statuses = [v["status"] for v in cp["items"].values()]
    return {
        "total": len(statuses),
        "done": statuses.count("done"),
        "skipped": statuses.count("skipped"),
        "in_progress": statuses.count("in_progress"),
        "pending": statuses.count("pending"),
    }
