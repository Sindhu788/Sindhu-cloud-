"""Memory Core (Grand Master Prompt, Phase 1.9): a readable index of the
project's checkpoint files, so past decisions/results don't require
opening raw JSON files by hand to find. Read-only -- never writes,
renames, or deletes a checkpoint file. Recent session/decision history
(activity_log, audit_trail_log) already has its own working endpoints
(see sindhu_web/api/activity.py) and is reused as-is by the frontend
page, not duplicated here.
"""
import json
import os
from datetime import datetime, timezone

from fastapi import APIRouter

from data_engine.paths import DATA_DIR

router = APIRouter()

CHECKPOINTS_DIR = os.path.join(DATA_DIR, "checkpoints")


def _describe(path, filename):
    stat = os.stat(path)
    entry = {
        "filename": filename,
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "task": None,
        "status": None,
        "parse_ok": False,
    }
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        entry["parse_ok"] = True
        if isinstance(doc, dict):
            for key in ("task", "status", "started", "started_at", "current_phase", "next_item_to_resume"):
                val = doc.get(key)
                if isinstance(val, (str, int, float, bool)) or val is None:
                    entry[key] = val
    except (OSError, json.JSONDecodeError):
        pass
    return entry


@router.get("/api/memory-core/checkpoints")
def list_checkpoints():
    if not os.path.isdir(CHECKPOINTS_DIR):
        return {"checkpoints": [], "total_count": 0, "directory_exists": False}
    files = [f for f in os.listdir(CHECKPOINTS_DIR) if f.lower().endswith(".json")]
    entries = [_describe(os.path.join(CHECKPOINTS_DIR, f), f) for f in files]
    entries.sort(key=lambda e: e["modified_at"], reverse=True)
    return {"checkpoints": entries, "total_count": len(entries), "directory_exists": True}
