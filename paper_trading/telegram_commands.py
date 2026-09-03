"""Telegram Bot Commands (Grand Feature Expansion, Phase 2 Features 20-21):
/status, /pause, /resume, /help -- read and control the Paper Trading
engine directly from Telegram. This is the first INCOMING Telegram
integration anywhere in this codebase; every previous piece of code only
ever SENDS (see telegram_bot.py's _raw_send).

Long-polling (Telegram's getUpdates), not a webhook -- works identically
whether this runs on the local laptop (which has no public URL at all) or
the cloud (which does have one, but a webhook would only work there, and
this exact engine-control code needs to behave the same in both places).

SECURITY: a command is only ever honored if it comes from the exact
chat_id configured as telegram_bot's own `channel_id` setting -- the same
destination every outbound signal already goes to. Every other sender's
message is silently ignored (no reply at all, not even an error), so this
bot can never be discovered or driven by a stranger who happens to find
its username.

/pause and /resume call the EXACT SAME engine.start()/stop() the dashboard
buttons already call -- they inherit every existing protection for free
(the kill switch refuses engine.start() while active; the account-wide
drawdown breaker only ever blocks NEW trades, never the engine itself,
matching the dashboard's own behavior)."""

import threading
import time

import requests

from data_engine.logging_setup import log as default_log
from paper_trading import config as pt_config, telegram_bot

POLL_TIMEOUT_SECONDS = 25
_last_update_id = None


def _bot_token():
    return telegram_bot.load_settings().get("bot_token")


def _api_url(method):
    return f"https://api.telegram.org/bot{_bot_token()}/{method}"


def _get_updates(offset):
    token = _bot_token()
    if not token:
        return []
    params = {"timeout": POLL_TIMEOUT_SECONDS}
    if offset is not None:
        params["offset"] = offset
    try:
        resp = requests.get(_api_url("getUpdates"), params=params, timeout=POLL_TIMEOUT_SECONDS + 10)
        if resp.status_code != 200:
            return []
        return resp.json().get("result", [])
    except requests.RequestException:
        return []


def _reply(chat_id, text):
    if not _bot_token():
        return
    try:
        requests.post(_api_url("sendMessage"), json={"chat_id": chat_id, "text": text}, timeout=15)
    except requests.RequestException:
        pass


def _is_authorized(chat_id):
    configured = telegram_bot.load_settings().get("channel_id")
    return bool(configured) and str(chat_id) == str(configured)


def _status_reply():
    from paper_trading import account_drawdown_guard, kill_switch
    from paper_trading.engine import engine
    status = engine.status()
    ks = kill_switch.status()
    dd = account_drawdown_guard.status()
    lines = [
        f"Engine: {'RUNNING' if status['running'] else 'STOPPED'}",
        f"Dry Run: {'ON' if status['dry_run'] else 'OFF'}",
        f"Open trades: {status['open_trades']}",
        f"Combined balance: ${status['balance']:.2f}",
    ]
    if ks["active"]:
        lines.append(f"\U0001F6D1 KILL SWITCH ACTIVE: {ks['reason']}")
    if dd["paused"]:
        lines.append(f"⛔ Account-wide drawdown pause ACTIVE: {dd['paused_reason']}")
    return "\n".join(lines)


def _pause_reply():
    from paper_trading.engine import engine
    if not engine.is_running():
        return "Engine is already stopped."
    engine.stop()
    pt_config.update(engine_enabled=False)
    from sindhu_web import sync
    sync.notify("paper_trading", "stopped", "Paper Trading engine stopped via Telegram /pause")
    return "Engine stopped."


def _resume_reply():
    from paper_trading.engine import engine
    if engine.is_running():
        return "Engine is already running."
    try:
        engine.start()
    except RuntimeError as e:
        return f"Could not resume: {e}"
    pt_config.update(engine_enabled=True)
    from sindhu_web import sync
    sync.notify("paper_trading", "started", "Paper Trading engine started via Telegram /resume")
    return "Engine started."


def _help_reply():
    return (
        "Available commands:\n"
        "/status -- engine state, open trades, balance, kill switch / drawdown pause status\n"
        "/pause -- stop the engine (same as the dashboard's Stop Engine button)\n"
        "/resume -- start the engine (same as the dashboard's Start Engine button)\n"
        "/help -- this message"
    )


_COMMANDS = {"/status": _status_reply, "/pause": _pause_reply, "/resume": _resume_reply, "/help": _help_reply}


def handle_update(update):
    """Returns the reply text if a recognized, authorized command was
    handled, else None. Nothing is sent back for an unauthorized sender OR
    an unrecognized command -- this never behaves like a public echo bot."""
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = (message.get("text") or "").strip().split("@")[0]  # strip a group chat's /cmd@botname suffix

    if not chat_id or not _is_authorized(chat_id):
        return None
    handler = _COMMANDS.get(text)
    if not handler:
        return None
    reply = handler()
    _reply(chat_id, reply)
    return reply


def poll_once():
    """One long-poll round trip. Returns how many updates were received
    (processed or not) -- used by tests and for a simple health signal."""
    global _last_update_id
    offset = _last_update_id + 1 if _last_update_id is not None else None
    updates = _get_updates(offset)
    for update in updates:
        _last_update_id = update["update_id"]
        try:
            handle_update(update)
        except Exception as e:
            default_log(f"[telegram-commands] error handling update: {e!r}")
    return len(updates)


def start_command_polling_thread():
    """Runs once at server startup (local and cloud both -- see
    sindhu_web/server.py and cloud_runtime/app.py). A long-poll call
    already blocks for up to POLL_TIMEOUT_SECONDS waiting for a new
    message, so no extra sleep is needed between successful iterations --
    only when there is no bot token configured yet, or after an error."""

    def _loop():
        while True:
            try:
                if _bot_token():
                    poll_once()
                else:
                    time.sleep(30)
            except Exception as e:
                default_log(f"[telegram-commands] poll error: {e!r}")
                time.sleep(5)

    threading.Thread(target=_loop, daemon=True).start()
