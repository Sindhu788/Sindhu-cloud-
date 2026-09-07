"""Master Task Expansion, Part 4: Simple Paper-Trading Status Ping.

GOAL: a simple, low-effort way for the CEO to always know, at a glance,
whether Paper Trading is actually running -- a periodic PRIVATE Telegram
message (never the public/shared channel) plus a dashboard badge (the
dashboard badge itself lives in sindhu_web/static/js/app.js's existing
topbar/engine-status-banner, extended to also show Telegram/live-candles
status; this module is the Telegram-ping half).

Runs on BOTH the local app and the cloud runner (wired from each one's own
lifespan) -- Paper Trading, its balance, and its open trades are all
deployment-specific state, so each deployment that has a personal_chat_id
configured pings about ITS OWN engine, independently. Reuses:
  * paper_trading.engine.engine.status() -- already computes running/
    balance/open_trades/last_tick_at, no new state.
  * paper_trading.telegram_bot.send_private_message() -- the exact private-
    DM delivery path this task's own Part 6/prior-session work already
    built for the Emergency Downtime Alert and Weekly/Monthly Reports.
  * The same "check hourly, send only once the real interval has elapsed"
    scheduling convention already used by paper_trading/cloud_sync.py and
    paper_trading/daily_report.py -- never a raw multi-hour sleep, which
    would not notice a delayed process start or catch up after a restart.

If personal_chat_id isn't configured yet, this never sends anything and
never silently pretends to have -- send_status_ping_now() returns
{"skipped": True, "reason": ...} in that case (see this task's own
instruction: flag as blocking, don't guess or skip silently).
"""
import threading
from datetime import datetime, timezone

from data_engine import config as base_config
from data_engine.logging_setup import log as default_log

_STATE_FILE = "status_ping_state.json"
_STATE_DEFAULTS = {"last_sent_at": None}
PING_INTERVAL_SECONDS = 5 * 3600  # every ~5 hours -- within the requested 4-6h window
_CHECK_INTERVAL_SECONDS = 3600  # hourly gate check, same convention as cloud_sync.py
STUCK_THRESHOLD_SECONDS = 30 * 60  # no tick in 30+ min while "running" is treated as stuck --
                                    # a single full tick (all coins x all strategies) can
                                    # legitimately take several minutes, so this is deliberately
                                    # generous rather than flagging a normal slow tick as stuck.

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


def build_status_message():
    """Returns (message_text, is_warning). Real numbers only, straight from
    the engine's own status() -- nothing estimated."""
    from paper_trading.engine import engine

    status = engine.status()
    running = status["running"]
    last_tick_at = status.get("last_tick_at")

    stuck = False
    if running and last_tick_at:
        try:
            last = datetime.fromisoformat(last_tick_at)
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            stuck = (datetime.now(timezone.utc) - last).total_seconds() > STUCK_THRESHOLD_SECONDS
        except ValueError:
            pass

    lines = ["SINDHU Paper Trading -- Status Ping"]
    if not running:
        lines.append("Paper Trading is currently OFF.")
    elif stuck:
        lines.append(f"Paper Trading looks STUCK -- no tick recorded since {last_tick_at}.")
    else:
        lines.append("Paper Trading is running normally.")
    lines.append(f"Balance: {status['balance']:.2f}")
    lines.append(f"Open trades: {status['open_trades']}")
    lines.append(f"Last tick: {last_tick_at or 'never'}")
    return "\n".join(lines), (not running or stuck)


def send_status_ping_now():
    """Real, callable-on-demand send -- used by the scheduler, a manual
    dashboard trigger, and tests. Never silently no-ops: returns
    {"skipped": True, "reason": ...} when personal_chat_id isn't configured,
    rather than pretending a ping went out."""
    from paper_trading import telegram_bot

    settings = telegram_bot.load_settings()
    if not settings.get("personal_chat_id"):
        return {"ok": False, "skipped": True, "reason": "no personal_chat_id configured yet"}

    message, is_warning = build_status_message()
    result = telegram_bot.send_private_message(message)
    _save_state(last_sent_at=_now_iso())
    return {**result, "skipped": False, "is_warning": is_warning}


def _should_send_now():
    last_sent_at = get_state().get("last_sent_at")
    if not last_sent_at:
        return True
    try:
        last = datetime.fromisoformat(last_sent_at)
    except ValueError:
        return True
    return (datetime.now(timezone.utc) - last).total_seconds() >= PING_INTERVAL_SECONDS


def _loop():
    default_log(f"[status-ping] scheduler started -- checks hourly, sends a private status "
                f"ping at most once every {PING_INTERVAL_SECONDS}s.")
    while not _stop_flag.is_set():
        try:
            if _should_send_now():
                result = send_status_ping_now()
                if result.get("skipped"):
                    default_log("[status-ping] skipped -- personal_chat_id not configured yet.")
                elif result.get("ok"):
                    default_log("[status-ping] sent" + (" (WARNING: engine off/stuck)" if result.get("is_warning") else "") + ".")
                else:
                    default_log(f"[status-ping] send failed: {result}")
        except Exception as e:
            default_log(f"[status-ping] check failed: {e!r}")
        _stop_flag.wait(_CHECK_INTERVAL_SECONDS)


def start_scheduler_thread():
    """Call once from each deployment's own lifespan (both sindhu_web/
    server.py and cloud_runtime/app.py -- Paper Trading state is
    deployment-specific, so each deployment pings about its own engine)."""
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop_flag.clear()
    _thread = threading.Thread(target=_loop, daemon=True)
    _thread.start()


def stop_scheduler_thread():
    _stop_flag.set()
