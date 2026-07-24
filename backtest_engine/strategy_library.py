"""Strategy library: save/load/rename/duplicate/delete/favourite/search/tag
saved strategies, with full version history. Each strategy is a folder
under strategies/library/<id>/ -- meta.json for catalog info, versions/vN.json
for each saved snapshot of the StrategyConfig (so nothing is ever lost when
a strategy is edited and re-saved)."""

import json
import os
import shutil
import uuid
from datetime import datetime, timezone

from backtest_engine.strategy_config import StrategyConfig
from backtest_engine.strategy_safety_check import run_safety_check

_LIBRARY_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "strategies", "library"
)


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _strategy_dir(strategy_id):
    return os.path.join(_LIBRARY_DIR, strategy_id)


def _meta_path(strategy_id):
    return os.path.join(_strategy_dir(strategy_id), "meta.json")


def _versions_dir(strategy_id):
    return os.path.join(_strategy_dir(strategy_id), "versions")


def _read_meta(strategy_id):
    with open(_meta_path(strategy_id), "r", encoding="utf-8") as f:
        return json.load(f)


def _write_meta(strategy_id, meta):
    with open(_meta_path(strategy_id), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)


def create(config, tags=None):
    """Saves a new strategy as version 1. Returns its library id.

    Automatic Strategy Safety Check: runs on every save (new strategy or
    new version of an existing one) so a strategy's "ready"/"needs_review"
    status is always current, without any caller having to remember to
    call it separately -- covers every creation path (manual import, AI
    import, pasted strategy, optimizer's winning candidate saved via
    save_version) through this one choke point."""
    os.makedirs(_LIBRARY_DIR, exist_ok=True)
    strategy_id = uuid.uuid4().hex[:12]
    os.makedirs(_versions_dir(strategy_id), exist_ok=True)

    safety = run_safety_check(config)
    now = _now_iso()
    meta = {
        "id": strategy_id,
        "name": config.name,
        "tags": tags or [],
        "favourite": False,
        "created_at": now,
        "updated_at": now,
        "current_version": 1,
        "safety_status": safety["status"],
        "safety_reasons": safety["reasons"],
    }
    _write_meta(strategy_id, meta)
    with open(os.path.join(_versions_dir(strategy_id), "v1.json"), "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=2)

    return strategy_id


def save_version(strategy_id, config):
    """Appends a new version to an existing strategy (edit history)."""
    meta = _read_meta(strategy_id)
    new_version = meta["current_version"] + 1
    with open(os.path.join(_versions_dir(strategy_id), f"v{new_version}.json"), "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=2)
    safety = run_safety_check(config)
    meta["current_version"] = new_version
    meta["updated_at"] = _now_iso()
    meta["name"] = config.name
    meta["safety_status"] = safety["status"]
    meta["safety_reasons"] = safety["reasons"]
    _write_meta(strategy_id, meta)
    return new_version


def recheck_safety(strategy_id):
    """Re-runs the safety check against a strategy's CURRENT version and
    updates meta.json in place, without creating a new version -- used by
    the one-time backfill over strategies saved before this check existed.
    Returns the safety result dict."""
    meta = _read_meta(strategy_id)
    config = load(strategy_id)
    safety = run_safety_check(config)
    meta["safety_status"] = safety["status"]
    meta["safety_reasons"] = safety["reasons"]
    _write_meta(strategy_id, meta)
    return safety


def load(strategy_id, version=None):
    meta = _read_meta(strategy_id)
    version = version or meta["current_version"]
    path = os.path.join(_versions_dir(strategy_id), f"v{version}.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    config = StrategyConfig.from_dict(data)
    config.tags = meta.get("tags", [])
    config.favourite = meta.get("favourite", False)
    return config


def list_all():
    if not os.path.isdir(_LIBRARY_DIR):
        return []
    result = []
    for strategy_id in sorted(os.listdir(_LIBRARY_DIR)):
        if os.path.isfile(_meta_path(strategy_id)):
            result.append(_read_meta(strategy_id))
    return result


def find_by_name(name):
    """Case-insensitive exact-name lookup against every saved strategy's
    meta.json. Returns the matching strategy_id, or None. Used so saving a
    strategy with the same name as an existing one updates it as a new
    version instead of silently creating a duplicate."""
    target = (name or "").strip().lower()
    if not target:
        return None
    for meta in list_all():
        if meta["name"].strip().lower() == target:
            return meta["id"]
    return None


def search(query="", tag=None):
    query = query.lower().strip()
    results = []
    for meta in list_all():
        if tag and tag not in meta.get("tags", []):
            continue
        if query and query not in meta["name"].lower() and not any(query in t.lower() for t in meta.get("tags", [])):
            continue
        results.append(meta)
    return results


def rename(strategy_id, new_name):
    meta = _read_meta(strategy_id)
    meta["name"] = new_name
    meta["updated_at"] = _now_iso()
    _write_meta(strategy_id, meta)


def set_tags(strategy_id, tags):
    meta = _read_meta(strategy_id)
    meta["tags"] = list(tags)
    meta["updated_at"] = _now_iso()
    _write_meta(strategy_id, meta)


def set_favourite(strategy_id, favourite):
    meta = _read_meta(strategy_id)
    meta["favourite"] = bool(favourite)
    _write_meta(strategy_id, meta)


def duplicate(strategy_id, new_name=None):
    src_meta = _read_meta(strategy_id)
    new_id = uuid.uuid4().hex[:12]
    shutil.copytree(_strategy_dir(strategy_id), _strategy_dir(new_id))

    now = _now_iso()
    new_meta = dict(src_meta)
    new_meta["id"] = new_id
    new_meta["name"] = new_name or f"{src_meta['name']} (copy)"
    new_meta["favourite"] = False
    new_meta["created_at"] = now
    new_meta["updated_at"] = now
    _write_meta(new_id, new_meta)
    return new_id


def delete(strategy_id):
    """ignore_errors=False (the default) on purpose: a silent partial
    failure here (e.g. a locked file on Windows) previously left a
    half-deleted strategy folder -- meta.json present, versions/ gone --
    which the API then reported as "deleted" while it actually still
    existed in a newly-corrupted state. Better to raise and let the
    caller see the real error than to lie about success."""
    path = _strategy_dir(strategy_id)
    if os.path.isdir(path):
        shutil.rmtree(path)


def set_clarification(strategy_id, data):
    """Persists (or clears, if data is None) the "why this strategy needs
    clarification" record directly on the strategy's own meta.json --
    independent of the originating compiled_document, which has no reverse
    index from strategy_id back to it (see knowledge_compiler/compiler.py's
    _finalize_and_save_strategy). `data` shape (when not None):
    {"notes": [str], "hidden_rules": [{"field","confidence","reason","evidence"}],
     "confidence_pct": float|None, "updated_at": iso}. Cleared automatically
    once a strategy re-validates as READY_FOR_BACKTEST so a resolved
    strategy never keeps showing stale clarification data."""
    meta = _read_meta(strategy_id)
    if data is None:
        meta.pop("clarification", None)
    else:
        meta["clarification"] = data
    _write_meta(strategy_id, meta)


def get_clarification(strategy_id):
    try:
        meta = _read_meta(strategy_id)
    except FileNotFoundError:
        return None
    return meta.get("clarification")


def version_history(strategy_id):
    versions = []
    vdir = _versions_dir(strategy_id)
    if not os.path.isdir(vdir):
        return versions
    for fname in sorted(os.listdir(vdir), key=lambda n: int(n[1:-5])):
        version_num = int(fname[1:-5])
        mtime = os.path.getmtime(os.path.join(vdir, fname))
        versions.append({
            "version": version_num,
            "modified_at": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(),
        })
    return versions
