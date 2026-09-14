"""Master Task Expansion, Part 1: Local -> Cloud Strategy Sync (config-only).

GOAL (see data/checkpoints/master_task_expansion.json for the full design
notes): when a strategy is built/improved locally, its small StrategyConfig
blueprint -- never the backtest engine, Evolution Engine, Self-Learning
Engine, historical candles, or the full local database -- should be able to
reach the cloud deployment's paper-trading engine safely.

Two sides live in this one module, mirroring how paper_trading/telegram_bot.py
and paper_trading/cloud_sync.py already share one file between their local
and cloud-side behavior:

  * push_strategy_to_cloud() -- runs on the LOCAL machine. Loads a strategy,
    runs it through the SAME two gates every other paper-trading activation
    in this codebase already requires (validator.validate() +
    strategy_safety_check.run_safety_check() -- the exact pair the
    precedent activation script used), and only if both pass, POSTs the
    small config JSON to the cloud's receive endpoint.

  * receive_synced_strategy() -- runs on the CLOUD. Re-validates the SAME
    two gates server-side (never trusts the sender, even though the sender
    is the CEO's own machine) and, only if both pass, stores the config via
    the existing cloud_settings key-value store (no new DB table) and
    ensures a paper_strategy_config row exists so the existing paper-trading
    engine picks it up on its very next tick through strategy_matcher.py --
    no new cloud-side trading logic at all.

AUTH: this needs its own secret, separate from the browser dashboard's
X-Sindhu-Token (see sindhu_web/security.py) -- a CLI/scheduled sync script
has no browser session to obtain that token from. get_or_create_sync_secret()
mirrors security.get_or_create_token()'s exact persistence pattern (Postgres
cloud_settings when deployed, a local JSON file otherwise) but is a wholly
separate secret. Viewing it still requires a real logged-in dashboard call
(GET /api/paper-trading/strategy-sync/secret, behind the normal login+token
gate) -- only USING it afterward skips the browser session.
"""
import json
import os
import secrets
from datetime import datetime, timedelta, timezone

from backtest_engine import strategy_library as lib
from backtest_engine import validator
from backtest_engine.strategy_config import StrategyConfig
from backtest_engine.strategy_safety_check import run_safety_check
from data_engine import config as base_config, db_backend, storage
from data_engine.paths import ensure_folders

_SYNC_SECRET_CLOUD_KEY = "strategy_sync_secret"
_SYNC_SECRET_LOCAL_FILE = "strategy_sync_secret.json"
_SYNCED_STRATEGY_KEY_PREFIX = "synced_strategy:"
_TARGET_CONFIG_FILE = "cloud_sync_target.json"
_TARGET_DEFAULTS = {"cloud_url": "https://sindhu-cloud-1.onrender.com", "sync_secret": ""}
_AUDIT_ENTITY = "strategy_sync"

_BANDWIDTH_STATS_KEY = "strategy_sync_bandwidth"
_BANDWIDTH_STATS_FILE = "strategy_sync_bandwidth.json"
_BANDWIDTH_DEFAULTS = {"total_bytes_sent": 0, "push_count": 0}

_OFFLINE_QUEUE_KEY = "strategy_sync_offline_queue"
_OFFLINE_QUEUE_FILE = "strategy_sync_offline_queue.json"
_OFFLINE_QUEUE_DEFAULTS = {"queued": []}


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------- secret

def get_or_create_sync_secret():
    """See module docstring's AUTH note. Cloud-side (Postgres) persists in
    cloud_settings so it survives restarts/redeploys, exactly like
    sindhu_web.security.get_or_create_token(); local-side falls back to a
    plain JSON file under data/config/, same as every other local-only
    settings file in this project."""
    if db_backend.IS_POSTGRES:
        saved = storage.get_cloud_setting(_SYNC_SECRET_CLOUD_KEY)
        if saved and saved.get("secret"):
            return saved["secret"]
        secret = secrets.token_hex(16)
        storage.save_cloud_setting(_SYNC_SECRET_CLOUD_KEY, {"secret": secret}, _now_iso())
        return secret

    ensure_folders()
    path = os.path.join(base_config.CONFIG_DIR, _SYNC_SECRET_LOCAL_FILE)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)["secret"]
    secret = secrets.token_hex(16)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"secret": secret}, f)
    return secret


# --------------------------------------------------------- local-side push

def get_sync_target():
    """The local machine's own record of WHERE to push to and WITH WHAT
    secret -- entered once by the CEO (the cloud URL is pre-filled with the
    project's real deployment; the secret must be copied from the cloud
    dashboard's own logged-in view of get_or_create_sync_secret() above,
    since a script has no way to log in and fetch it itself)."""
    return base_config.load_or_seed(_TARGET_CONFIG_FILE, _TARGET_DEFAULTS)


def save_sync_target(cloud_url=None, sync_secret=None):
    current = get_sync_target()
    if cloud_url is not None:
        current["cloud_url"] = cloud_url.strip()
    if sync_secret is not None:
        current["sync_secret"] = sync_secret.strip()
    base_config.save_config(_TARGET_CONFIG_FILE, current)
    return current


def push_strategy_to_cloud(strategy_id, cloud_url=None, sync_secret=None, timeout=30, include_settings=False):
    """LOCAL side. Always logs the attempt to the LOCAL audit trail
    (entity='strategy_sync') regardless of outcome, so the local dashboard
    has a durable, honest record even when the network call itself never
    goes out (e.g. validation failed before anything was sent).

    Phase 7 Item 24 (selective sync): `include_settings=True` additionally
    carries this machine's own local paper_strategy_config row (enabled/
    priority/supported_coins/supported_market_types) alongside the
    strategy blueprint, for a CEO who explicitly wants the cloud's trading
    settings to start out matching the local ones -- off by default, since
    the existing behavior (cloud keeps whatever it already decided for an
    already-configured strategy_id) is the safer one. Trades, history, and
    the rest of the database are never selectable -- see the module
    docstring; that boundary is permanent, not a sync option."""
    import requests

    target = get_sync_target()
    cloud_url = (cloud_url or target["cloud_url"]).rstrip("/")
    sync_secret = sync_secret or target["sync_secret"]
    now = _now_iso()

    if not sync_secret:
        storage.record_audit_event(_AUDIT_ENTITY, "failed",
                                    f"{strategy_id}: no sync secret configured -- log into the cloud dashboard once "
                                    f"to fetch it, then save it in Settings", now)
        return {"ok": False, "error": "no sync secret configured"}

    try:
        config = lib.load(strategy_id)
        meta = lib.get_meta(strategy_id)
    except FileNotFoundError:
        storage.record_audit_event(_AUDIT_ENTITY, "failed", f"{strategy_id}: not found in the local library", now)
        return {"ok": False, "error": "strategy not found locally"}

    errors = validator.validate(config)
    if errors:
        storage.record_audit_event(_AUDIT_ENTITY, "failed",
                                    f"{strategy_id}: validator rejected -- {'; '.join(errors)}", now)
        return {"ok": False, "error": "validation failed", "errors": errors}

    safety = run_safety_check(config)
    if not safety["passed"]:
        storage.record_audit_event(_AUDIT_ENTITY, "failed",
                                    f"{strategy_id}: safety check needs review -- {'; '.join(safety['reasons'])}", now)
        return {"ok": False, "error": "safety check failed", "reasons": safety["reasons"]}

    payload = {
        "strategy_id": strategy_id,
        "name": meta.get("name", strategy_id),
        "tags": meta.get("tags", []),
        "config_json": config.to_dict(),
        # Phase 7 Items 23+28: lets the cloud tell a genuinely newer local
        # push apart from a stale/out-of-order one, instead of blind-overwriting.
        "local_version": meta.get("current_version"),
        "local_updated_at": meta.get("updated_at"),
    }
    if include_settings:
        local_settings = storage.get_paper_strategy_config(strategy_id)
        if local_settings:
            payload["settings"] = {
                "enabled": local_settings.get("enabled"), "priority": local_settings.get("priority"),
                "supported_coins": local_settings.get("supported_coins") or [],
                "supported_market_types": local_settings.get("supported_market_types") or [],
            }
    payload_bytes = len(json.dumps(payload).encode("utf-8"))

    try:
        resp = requests.post(
            f"{cloud_url}/api/paper-trading/strategy-sync/push",
            json=payload, headers={"X-Sindhu-Sync-Secret": sync_secret}, timeout=timeout,
        )
    except requests.RequestException as e:
        storage.record_audit_event(_AUDIT_ENTITY, "failed", f"{strategy_id}: network error -- {e!r}", now)
        # Phase 7 Item 26: an offline/unreachable cloud is not a rejection --
        # queue it so a later flush_offline_queue() (scheduler thread or the
        # next successful reconnect) can retry without the CEO re-clicking.
        _enqueue_offline(strategy_id, include_settings=include_settings)
        return {"ok": False, "error": f"network error: {e}"}

    if resp.status_code != 200:
        detail = resp.text[:300]
        storage.record_audit_event(_AUDIT_ENTITY, "failed",
                                    f"{strategy_id}: cloud rejected -- HTTP {resp.status_code}: {detail}", now)
        return {"ok": False, "error": f"cloud rejected: HTTP {resp.status_code}", "detail": detail}

    _record_bandwidth(payload_bytes)
    storage.record_audit_event(
        _AUDIT_ENTITY, "success",
        f"{strategy_id} ({meta.get('name')}) synced to cloud ({payload_bytes} bytes)", now,
    )
    return {"ok": True, "response": resp.json(), "bytes_sent": payload_bytes}


# --------------------------------------------------------- cloud-side receive

def receive_synced_strategy(strategy_id, name, tags, config_json, provided_secret,
                             local_version=None, local_updated_at=None, settings=None):
    """CLOUD side. Returns (result_dict, http_status). Never trusts the
    sender -- re-runs the identical validator + safety-check gate the local
    side already ran, so a tampered or buggy client can never push an
    unsafe config just because it knows the secret.

    Phase 7 Items 23+28 (safe two-way merge + conflict log): previously
    this blind-overwrote whatever cloud_settings row already existed for
    strategy_id, with no check at all -- an out-of-order or stale push
    (e.g. two machines syncing the same id, or a delayed retry landing
    after a newer push already went through) could silently clobber the
    more current version with an older one and leave no trace. Now, if a
    prior synced record exists AND both it and the incoming push carry a
    local_version, an incoming version that is NOT strictly newer is
    treated as a conflict: the existing cloud record is kept as-is (the
    safe default -- never let an older push win) and a distinct 'conflict'
    audit event is recorded so get_sync_log()/the conflicts view shows
    exactly what happened and how it was resolved. A push with no
    local_version (older client) or a genuinely first-time id is never a
    conflict and proceeds exactly as before."""
    expected = get_or_create_sync_secret()
    now = _now_iso()
    if not provided_secret or provided_secret != expected:
        storage.record_audit_event(_AUDIT_ENTITY, "failed", f"{strategy_id}: rejected -- invalid sync secret", now)
        return {"ok": False, "error": "invalid or missing sync secret"}, 401

    try:
        config = StrategyConfig.from_dict(config_json)
    except Exception as e:
        storage.record_audit_event(_AUDIT_ENTITY, "failed", f"{strategy_id}: malformed config -- {e!r}", now)
        return {"ok": False, "error": f"malformed config: {e}"}, 400

    errors = validator.validate(config)
    if errors:
        storage.record_audit_event(_AUDIT_ENTITY, "failed",
                                    f"{strategy_id}: validator rejected -- {'; '.join(errors)}", now)
        return {"ok": False, "error": "validation failed", "errors": errors}, 400

    safety = run_safety_check(config)
    if not safety["passed"]:
        storage.record_audit_event(_AUDIT_ENTITY, "failed",
                                    f"{strategy_id}: safety check needs review -- {'; '.join(safety['reasons'])}", now)
        return {"ok": False, "error": "safety check failed", "reasons": safety["reasons"]}, 400

    existing = storage.get_cloud_setting(_SYNCED_STRATEGY_KEY_PREFIX + strategy_id)
    existing_version = (existing or {}).get("local_version")
    is_conflict = (
        existing is not None
        and existing_version is not None
        and local_version is not None
        and local_version <= existing_version
        and (existing or {}).get("local_updated_at") != local_updated_at
    )
    if is_conflict:
        storage.record_audit_event(
            _AUDIT_ENTITY, "conflict",
            f"{strategy_id}: incoming push (local v{local_version}) is not newer than the stored "
            f"cloud record (v{existing_version}) -- kept the existing cloud record, incoming push discarded",
            now,
        )
        return {"ok": True, "strategy_id": strategy_id, "conflict": True,
                "resolution": "kept existing cloud record", "cloud_version": existing_version,
                "incoming_version": local_version}, 200

    record = {"strategy_id": strategy_id, "name": name, "tags": tags or [],
              "config_json": config_json, "synced_at": now,
              "local_version": local_version, "local_updated_at": local_updated_at}
    storage.save_cloud_setting(_SYNCED_STRATEGY_KEY_PREFIX + strategy_id, record, now)

    # Builder default, flagged in the checkpoint: a newly-synced strategy is
    # auto-enabled for paper trading (the task's own stated goal -- "the
    # cloud should be able to start paper-trading it"), same default
    # enabled=True/priority=5 every other new paper_strategy_config row in
    # this codebase already uses. Re-syncing an UPDATED version of a
    # strategy the CEO has since manually disabled/reprioritized never
    # overwrites that choice -- only a genuinely first-time id gets the
    # default row.
    already_configured = strategy_id in storage.list_paper_strategy_configs()
    if not already_configured:
        # Phase 7 Item 24 (selective sync): an explicitly pushed `settings`
        # blob overrides the hardcoded enabled=True/priority=5 default --
        # still only ever applied to a genuinely first-time strategy_id,
        # same protection as the plain default a line above already had.
        settings = settings or {}
        storage.save_paper_strategy_config(
            strategy_id,
            enabled=settings.get("enabled", True), priority=settings.get("priority", 5),
            supported_coins=settings.get("supported_coins") or [],
            supported_market_types=settings.get("supported_market_types") or [],
            now_iso=now,
        )

    storage.record_audit_event(_AUDIT_ENTITY, "success",
                                f"{strategy_id} ({name}) received and registered for paper trading"
                                + ("" if already_configured else " (newly enabled)"), now)
    return {"ok": True, "strategy_id": strategy_id, "newly_enabled": not already_configured}, 200


def get_synced_strategy(strategy_id):
    """CLOUD side only -- None locally (no cloud_settings table on SQLite),
    used by strategy_library.load_including_synced()."""
    if not db_backend.IS_POSTGRES:
        return None
    return storage.get_cloud_setting(_SYNCED_STRATEGY_KEY_PREFIX + strategy_id)


def list_synced_strategies():
    """CLOUD side only -- empty locally. Used by both
    strategy_library.list_all_including_synced() (so the paper-trading
    engine picks synced strategies up) and the dashboard's sync-status view."""
    if not db_backend.IS_POSTGRES:
        return []
    return [row["value"] for row in storage.list_cloud_settings_by_prefix(_SYNCED_STRATEGY_KEY_PREFIX)]


def get_sync_log(limit=50):
    """LOCAL dashboard's own record of what IT has pushed (see
    push_strategy_to_cloud()'s record_audit_event calls above) -- this is
    intentionally the LOCAL audit trail, not the cloud's, so it stays
    visible even without logging into the cloud dashboard. Whichever
    machine this runs on (local or cloud) shows THAT machine's own
    strategy_sync audit trail, so on the cloud deployment this is also
    where receive_synced_strategy()'s 'conflict' events show up."""
    return storage.list_audit_trail(limit=limit, entity=_AUDIT_ENTITY)


def list_sync_conflicts(limit=50):
    """Phase 7 Item 23: just the conflict-resolution subset of the sync
    log above, so the dashboard can surface "what happened when local/
    cloud disagreed and how it was resolved" without the caller filtering
    the full log client-side. Pulls a wider pool than `limit` before
    filtering -- conflicts are rare, so a plain entity-filtered LIMIT would
    often return zero even when real conflicts exist further back."""
    pool = storage.list_audit_trail(limit=max(limit * 20, 500), entity=_AUDIT_ENTITY)
    return [row for row in pool if row["action"] == "conflict"][:limit]


def get_sync_timeline(days=7):
    """Phase 7 Item 27: the flat sync log (whichever machine this runs on
    -- see get_sync_log()'s own note), bucketed into calendar days for the
    last `days` days, most recent day first -- same day-boundary grouping
    precedent as paper_trading.daily_missed_opportunity_report, just
    applied to the existing strategy_sync audit trail instead of the
    Near-Miss Log."""
    since_iso = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat() + "T00:00:00+00:00"
    rows = storage.list_audit_trail(limit=5000, entity=_AUDIT_ENTITY, since_iso=since_iso)
    buckets = {}
    for row in rows:
        day = (row["created_at"] or "")[:10]
        buckets.setdefault(day, []).append(row)
    return [{"day": day, "events": buckets[day]} for day in sorted(buckets.keys(), reverse=True)]


# --------------------------------------------------------------- bandwidth (Item 29)

def _record_bandwidth(num_bytes):
    stats = base_config.load_persistent(_BANDWIDTH_STATS_KEY, _BANDWIDTH_STATS_FILE, _BANDWIDTH_DEFAULTS)
    stats["total_bytes_sent"] = stats.get("total_bytes_sent", 0) + num_bytes
    stats["push_count"] = stats.get("push_count", 0) + 1
    base_config.save_persistent(_BANDWIDTH_STATS_KEY, _BANDWIDTH_STATS_FILE, stats)


def get_sync_bandwidth_stats():
    """Phase 7 Item 29: a running, permanent tally of how much has ever
    actually gone out over the wire for strategy syncs -- these payloads
    are always small (a single strategy's blueprint, never trades/candles/
    the database), but the CEO asked to be able to see that for themselves
    rather than take it on faith."""
    stats = base_config.load_persistent(_BANDWIDTH_STATS_KEY, _BANDWIDTH_STATS_FILE, _BANDWIDTH_DEFAULTS)
    total = stats.get("total_bytes_sent", 0)
    count = stats.get("push_count", 0)
    return {"total_bytes_sent": total, "push_count": count,
            "average_bytes_per_push": round(total / count, 1) if count else 0}


# --------------------------------------------------------------- offline queue (Items 26+30)

def _load_offline_queue():
    return base_config.load_persistent(_OFFLINE_QUEUE_KEY, _OFFLINE_QUEUE_FILE, _OFFLINE_QUEUE_DEFAULTS)


def _save_offline_queue(data):
    base_config.save_persistent(_OFFLINE_QUEUE_KEY, _OFFLINE_QUEUE_FILE, data)


def _enqueue_offline(strategy_id, include_settings=False):
    data = _load_offline_queue()
    for item in data["queued"]:
        if item["strategy_id"] == strategy_id:
            item["include_settings"] = include_settings
            item["queued_at"] = _now_iso()
            _save_offline_queue(data)
            return
    data["queued"].append({"strategy_id": strategy_id, "include_settings": include_settings,
                            "queued_at": _now_iso()})
    _save_offline_queue(data)


def list_offline_queue():
    """LOCAL side: every push still waiting for a working connection to
    the cloud, oldest first (insertion order)."""
    return _load_offline_queue()["queued"]


def discard_from_offline_queue(strategy_id):
    """Phase 7 Item 30: the emergency "cloud is source of truth" override.
    Rather than keep retrying a queued local push the CEO no longer wants
    to fight for, this simply abandons it -- the cloud's own current copy
    of that strategy (if any) stays exactly as it is, uncontested, and
    this machine stops trying to overwrite it. Purely a local bookkeeping
    action; it never talks to the cloud. Returns True if something was
    actually removed."""
    data = _load_offline_queue()
    before = len(data["queued"])
    data["queued"] = [item for item in data["queued"] if item["strategy_id"] != strategy_id]
    _save_offline_queue(data)
    return before != len(data["queued"])


def flush_offline_queue(cloud_url=None, sync_secret=None, timeout=30):
    """Phase 7 Item 26: re-attempts every push queued by a prior network
    failure -- same "retry queue, never silently drop" precedent as
    paper_trading.telegram_bot.sweep_pending_telegram_retries(). Meant to
    be called periodically (a scheduler thread) and once explicitly right
    after the CEO saves a new Cloud Sync target, as an implicit "try now,
    you might be back online". A push that fails again for a REAL reason
    (validation/safety/cloud rejection, not connectivity) is dropped
    rather than retried forever on something retrying can never fix."""
    data = _load_offline_queue()
    queued_snapshot = list(data["queued"])
    still_queued, flushed, dropped = [], [], []
    for item in queued_snapshot:
        result = push_strategy_to_cloud(item["strategy_id"], cloud_url=cloud_url, sync_secret=sync_secret,
                                         timeout=timeout, include_settings=item.get("include_settings", False))
        if result.get("ok"):
            flushed.append(item["strategy_id"])
        elif (result.get("error") or "").startswith("network error"):
            still_queued.append(item)
        else:
            dropped.append(item["strategy_id"])
    data["queued"] = still_queued
    _save_offline_queue(data)
    return {"flushed": flushed, "still_queued": [i["strategy_id"] for i in still_queued], "dropped": dropped}


def start_offline_queue_scheduler_thread():
    """Phase 7 Item 26 ("auto-flush on reconnect"): runs once at server
    startup (LOCAL side only in practice -- an empty queue elsewhere is a
    harmless no-op every 10 minutes), same shape as telegram_bot.py's
    start_live_stats_scheduler_thread()."""
    import threading
    import time

    def _loop():
        while True:
            try:
                if _load_offline_queue()["queued"]:
                    flush_offline_queue()
            except Exception:
                pass
            time.sleep(600)

    threading.Thread(target=_loop, daemon=True).start()


# --------------------------------------------------------------- sync health check (Item 25)

def get_cloud_sync_state():
    """CLOUD side only: a minimal {strategy_id: {local_version, synced_at}}
    map for every synced strategy, for check_sync_health() below to diff
    against -- deliberately excludes config_json/tags/name, since the
    local side already has its own copy of those and only needs the
    version markers to detect drift."""
    if not db_backend.IS_POSTGRES:
        return {}
    return {r["strategy_id"]: {"local_version": r.get("local_version"), "synced_at": r.get("synced_at")}
            for r in list_synced_strategies()}


def check_sync_health(cloud_url=None, sync_secret=None, timeout=15):
    """Phase 7 Item 25: LOCAL side, meant to run once on dashboard load.
    Compares every strategy in the local library against what the cloud
    currently reports for it (via get_cloud_sync_state(), fetched over the
    same sync-secret-gated channel push_strategy_to_cloud already uses) so
    a real local/cloud mismatch -- an update that never made it across, or
    a push that silently failed some time ago -- is flagged proactively
    instead of only surfacing the next time it actually matters."""
    import requests

    target = get_sync_target()
    cloud_url = (cloud_url or target["cloud_url"]).rstrip("/")
    sync_secret = sync_secret or target["sync_secret"]
    if not sync_secret:
        return {"reachable": False, "error": "no sync secret configured"}

    try:
        resp = requests.get(
            f"{cloud_url}/api/paper-trading/strategy-sync/cloud-state",
            headers={"X-Sindhu-Sync-Secret": sync_secret}, timeout=timeout,
        )
    except requests.RequestException as e:
        return {"reachable": False, "error": f"network error: {e}"}
    if resp.status_code != 200:
        return {"reachable": False, "error": f"cloud rejected: HTTP {resp.status_code}"}

    cloud_state = resp.json().get("synced", {})
    local_meta_by_id = {m["id"]: m for m in lib.list_all()}

    in_sync, out_of_sync, local_only = [], [], []
    for sid, meta in local_meta_by_id.items():
        if sid not in cloud_state:
            local_only.append(sid)
            continue
        cloud_version = cloud_state[sid].get("local_version")
        if cloud_version is not None and cloud_version != meta.get("current_version"):
            out_of_sync.append({"strategy_id": sid, "local_version": meta.get("current_version"),
                                 "cloud_version": cloud_version})
        else:
            in_sync.append(sid)
    cloud_only = [sid for sid in cloud_state if sid not in local_meta_by_id]

    return {"reachable": True, "in_sync": in_sync, "out_of_sync": out_of_sync,
            "local_only": local_only, "cloud_only": cloud_only}
