"""Grand Master Prompt, Phase 3.7: Maintenance Mode -- one switch that
pauses Paper Trading AND Telegram sending together, and resumes both back
to exactly the state they were in before maintenance started (never
blindly forces both back ON on resume, e.g. if Telegram was already OFF
before maintenance began).

"Pause the scanner" is not a separate mechanism from "pause paper trading"
-- the paper-trading engine's own tick loop IS the scanner (see paper_
trading/engine.py's _tick()), so stopping the engine already covers it;
there is no third, independent thing to pause.

This is pure orchestration of two ALREADY-SAFE existing controls
(engine.stop()/start(), telegram_bot.save_settings(master_send_enabled=))
-- it introduces no new pause/resume primitive and touches no safety gate.
"""
from datetime import datetime, timezone

from data_engine import config as base_config

_STATE_FILE = "maintenance_mode_state.json"
_STATE_DEFAULTS = {
    "active": False, "entered_at": None, "entered_by": None,
    "was_engine_running": None, "was_telegram_enabled": None,
}


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def get_state():
    return base_config.load_or_seed(_STATE_FILE, _STATE_DEFAULTS)


def enter_maintenance_mode(actor="CEO"):
    from paper_trading.engine import engine
    from paper_trading import telegram_bot

    state = get_state()
    if state["active"]:
        return {"ok": False, "error": "Maintenance Mode is already active."}

    was_engine_running = engine.is_running()
    was_telegram_enabled = bool(telegram_bot.load_settings().get("master_send_enabled", True))

    if was_engine_running:
        engine.stop()
    if was_telegram_enabled:
        telegram_bot.save_settings(master_send_enabled=False)

    new_state = {
        "active": True, "entered_at": _now_iso(), "entered_by": actor,
        "was_engine_running": was_engine_running, "was_telegram_enabled": was_telegram_enabled,
    }
    base_config.save_config(_STATE_FILE, new_state)
    return {"ok": True, "state": new_state}


def exit_maintenance_mode(actor="CEO"):
    from paper_trading.engine import engine
    from paper_trading import telegram_bot

    state = get_state()
    if not state["active"]:
        return {"ok": False, "error": "Maintenance Mode is not currently active."}

    if state["was_engine_running"] and not engine.is_running():
        engine.start()
    if state["was_telegram_enabled"]:
        telegram_bot.save_settings(master_send_enabled=True)

    new_state = dict(_STATE_DEFAULTS)
    base_config.save_config(_STATE_FILE, new_state)
    return {"ok": True, "state": new_state, "resumed_by": actor}
