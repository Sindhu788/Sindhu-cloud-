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
from datetime import datetime, timezone

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


def push_strategy_to_cloud(strategy_id, cloud_url=None, sync_secret=None, timeout=30):
    """LOCAL side. Always logs the attempt to the LOCAL audit trail
    (entity='strategy_sync') regardless of outcome, so the local dashboard
    has a durable, honest record even when the network call itself never
    goes out (e.g. validation failed before anything was sent)."""
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
    }
    try:
        resp = requests.post(
            f"{cloud_url}/api/paper-trading/strategy-sync/push",
            json=payload, headers={"X-Sindhu-Sync-Secret": sync_secret}, timeout=timeout,
        )
    except requests.RequestException as e:
        storage.record_audit_event(_AUDIT_ENTITY, "failed", f"{strategy_id}: network error -- {e!r}", now)
        return {"ok": False, "error": f"network error: {e}"}

    if resp.status_code != 200:
        detail = resp.text[:300]
        storage.record_audit_event(_AUDIT_ENTITY, "failed",
                                    f"{strategy_id}: cloud rejected -- HTTP {resp.status_code}: {detail}", now)
        return {"ok": False, "error": f"cloud rejected: HTTP {resp.status_code}", "detail": detail}

    storage.record_audit_event(_AUDIT_ENTITY, "success", f"{strategy_id} ({meta.get('name')}) synced to cloud", now)
    return {"ok": True, "response": resp.json()}


# --------------------------------------------------------- cloud-side receive

def receive_synced_strategy(strategy_id, name, tags, config_json, provided_secret):
    """CLOUD side. Returns (result_dict, http_status). Never trusts the
    sender -- re-runs the identical validator + safety-check gate the local
    side already ran, so a tampered or buggy client can never push an
    unsafe config just because it knows the secret."""
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

    record = {"strategy_id": strategy_id, "name": name, "tags": tags or [],
              "config_json": config_json, "synced_at": now}
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
        storage.save_paper_strategy_config(strategy_id, enabled=True, priority=5,
                                            supported_coins=[], supported_market_types=[], now_iso=now)

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
    visible even without logging into the cloud dashboard."""
    return storage.list_audit_trail(limit=limit, entity=_AUDIT_ENTITY)
