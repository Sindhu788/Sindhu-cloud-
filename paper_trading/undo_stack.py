"""Grand Master Batch, Phase 4 Item 11: "Undo Last Action" -- reverses the
single most recent pause/disable/config-change action.

Deliberately scoped to a small, explicit set of KNOWN, safely-reversible
action types (a feature toggle flip, the master pause switch, a
per-strategy Drawdown Protection pause) rather than a generic "replay
arbitrary function" mechanism -- storing a real function reference or
serialized call would be either unsafe (eval/pickle-style risk) or need
a much larger undo-log redesign than this feature calls for. Each
action type's undo is a plain, explicit, testable branch below.

In-memory only (module-level, not persisted to the database or a
config file) -- "undo the thing I just did" is a short-lived intent
that does not need to survive a server restart, and keeping it in
memory avoids a permanent, ever-growing table for something that only
ever needs its single most recent entry.
"""

from datetime import datetime, timezone

_last_action = None


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def record(action_type, description, undo_data):
    """Called by the action itself, right after it succeeds, with enough
    data to reverse exactly this one change. Overwrites whatever was
    recorded before -- only the single most recent action is ever
    undoable, by design (this is not an undo history/stack)."""
    global _last_action
    _last_action = {"type": action_type, "description": description, "undo_data": undo_data, "at": _now_iso()}


def get_last_action():
    return _last_action


def clear():
    global _last_action
    _last_action = None


def undo_last_action():
    """Reverses whatever record() last captured. Returns {"ok": False,
    "error": ...} if there's nothing to undo or the action type is
    somehow unrecognized (should never happen for anything recorded by
    this module's own record() call sites)."""
    global _last_action
    if not _last_action:
        return {"ok": False, "error": "nothing to undo"}
    action = _last_action
    data = action["undo_data"]

    if action["type"] == "feature_toggle":
        from data_engine import feature_toggles
        feature_toggles.set_toggle(data["key"], data["previous_value"])
    elif action["type"] == "strategy_drawdown_pause":
        from paper_trading import drawdown_guard
        drawdown_guard.resume_strategy(data["strategy_id"])
    elif action["type"] == "kill_switch":
        from paper_trading import kill_switch
        kill_switch.deactivate(actor="Undo Last Action")
    else:
        return {"ok": False, "error": f"unrecognized undo action type: {action['type']}"}

    _last_action = None
    return {"ok": True, "undone": action}
