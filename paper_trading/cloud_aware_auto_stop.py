"""Master Task Expansion, Part 2: Cloud-Aware Local Auto-Stop.

GOAL: if the cloud deployment (sindhu-cloud-1) has BOTH Paper Trading AND
Telegram sending ON at the same time, the LOCAL paper-trading engine should
stop automatically -- running the same strategies live in two places at
once risks duplicate/conflicting trades and duplicate Telegram signals.

Runs ONLY on the local machine (started from sindhu_web/server.py's LOCAL
app lifespan, never from cloud_runtime/app.py -- the cloud has nothing
"more cloud" to watch, so this whole module is meaningless there). A
daemon thread checks the cloud's status every CHECK_INTERVAL_SECONDS (and
once immediately on startup, so a restart notices an already-both-on cloud
within seconds rather than waiting a full interval).

SAFETY, per this task's own explicit rules:
  * This ONLY ever calls engine.stop() -- never engine.start(). Resuming
    is a deliberate, separate CEO action (see resume_local_after_cloud_
    pause() and the dashboard's own "Resume Local Paper Trading" button),
    on purpose: auto-resuming trading is riskier than auto-stopping it.
  * Never touches paper_trading/config.py's "engine_enabled" persisted
    choice -- that represents the CEO's own last deliberate Start/Stop
    click (see paper_trading.engine.resume_engine_on_startup()). An
    auto-stop is a temporary, externally-driven pause, not a change to
    that standing preference, so a later server restart still tries to
    resume (and this module's own immediate startup check will re-pause
    it within seconds if the cloud is still both-on at that point).
  * Never touches the Evolution Engine, Self-Learning Engine, or
    backtesting -- only ever calls paper_trading.engine.engine.stop().
  * An unreachable cloud, or the cloud being reachable but NOT both-on,
    is never treated as grounds to stop anything.

AUTH: reuses the exact same X-Sindhu-Sync-Secret this task's Part 1 already
built (see paper_trading/strategy_sync.py) -- a scheduled local check has
no browser session to authenticate with, same reasoning as that module's
receive endpoint, and reusing the one existing secret avoids introducing
a second one for what is functionally the same "this local machine is
allowed to talk machine-to-machine with this cloud deployment" trust
relationship.
"""
import threading
from datetime import datetime, timezone

from data_engine import config as base_config
from data_engine.logging_setup import log as default_log

_STATE_FILE = "cloud_aware_auto_stop_state.json"
_STATE_DEFAULTS = {"paused_by_cloud": False, "paused_at": None,
                    "last_check_at": None, "last_check_result": None}
CHECK_INTERVAL_SECONDS = 300  # every 5 minutes

_stop_flag = threading.Event()
_thread = None


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def get_state():
    return base_config.load_or_seed(_STATE_FILE, _STATE_DEFAULTS)


def _save_state(**updates):
    state = get_state()
    state.update(updates)
    base_config.save_config(_STATE_FILE, state)
    return state


def check_cloud_status(cloud_url, sync_secret, timeout=10):
    """Real network call to the cloud's own status endpoint. Returns
    (paper_trading_running, telegram_sending_enabled), or (None, None) if
    unreachable/misconfigured -- NEVER treated as "both on" (see module
    docstring's safety notes), so a network hiccup can never itself
    trigger a stop."""
    import requests

    if not cloud_url or not sync_secret:
        return None, None
    try:
        resp = requests.get(
            cloud_url.rstrip("/") + "/api/paper-trading/cloud-status-for-auto-stop",
            headers={"X-Sindhu-Sync-Secret": sync_secret}, timeout=timeout,
        )
    except requests.RequestException:
        return None, None
    if resp.status_code != 200:
        return None, None
    try:
        data = resp.json()
    except ValueError:
        return None, None
    return data.get("paper_trading_running"), data.get("telegram_sending_enabled")


def check_and_maybe_stop_local():
    """The core check -- see module docstring for the full safety
    contract. Only ever stops; only ever acts on a definite "both ON"
    answer."""
    from paper_trading import strategy_sync  # local import: avoids importing
                                              # strategy_sync (and its own
                                              # backtest_engine imports) into
                                              # every caller of this module
    from paper_trading.engine import engine

    target = strategy_sync.get_sync_target()
    cloud_url, sync_secret = target.get("cloud_url"), target.get("sync_secret")
    now = _now_iso()

    pt_running, tg_enabled = check_cloud_status(cloud_url, sync_secret)
    if pt_running is None:
        _save_state(last_check_at=now, last_check_result="cloud unreachable or not configured -- no action taken")
        return

    both_on = bool(pt_running) and bool(tg_enabled)
    _save_state(last_check_at=now,
                last_check_result=f"cloud: paper_trading={pt_running}, telegram={tg_enabled}")

    if both_on and engine.is_running():
        if engine.stop():
            default_log("[cloud-aware-auto-stop] Local Paper Trading PAUSED -- the cloud deployment "
                        "has BOTH Paper Trading and Telegram ON right now, so this machine stopped "
                        "itself to avoid duplicate/conflicting trades. It will NOT resume on its own "
                        "-- use the dashboard's 'Resume Local Paper Trading' button once that changes.")
            _save_state(paused_by_cloud=True, paused_at=now)
    elif not both_on and get_state().get("paused_by_cloud"):
        # Per this task's own explicit instruction: clearing the reason
        # does NOT restart the engine. The CEO still has to click Resume.
        _save_state(paused_by_cloud=False)
        default_log("[cloud-aware-auto-stop] The cloud is no longer both Paper-Trading-and-Telegram ON -- "
                    "local Paper Trading may be resumed manually now. It will NOT restart on its own.")


def resume_local_after_cloud_pause():
    """Called by the dashboard's 'Resume Local Paper Trading' button
    (sindhu_web/api/paper_trading.py) right before it calls engine.start()
    itself -- this function only ever clears the paused-by-cloud state,
    never starts the engine (see module docstring)."""
    _save_state(paused_by_cloud=False)


def _loop():
    default_log(f"[cloud-aware-auto-stop] scheduler started -- checks the cloud's status "
                f"every {CHECK_INTERVAL_SECONDS}s (and once now).")
    while not _stop_flag.is_set():
        try:
            check_and_maybe_stop_local()
        except Exception as e:
            default_log(f"[cloud-aware-auto-stop] check failed: {e!r}")
        _stop_flag.wait(CHECK_INTERVAL_SECONDS)


def start_scheduler_thread():
    """Call once from sindhu_web/server.py's LOCAL app lifespan only."""
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop_flag.clear()
    _thread = threading.Thread(target=_loop, daemon=True)
    _thread.start()


def stop_scheduler_thread():
    _stop_flag.set()
