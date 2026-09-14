"""Grand Master Batch, Phase 6 Item 15: Signal Reaction Tracking (👍/👎).

Every real trade signal gets an inline 👍/👎 keyboard attached
(telegram_bot._raw_send's reply_markup, wired from send_signal_for_
position). A tap sends Telegram a callback_query update -- handled here,
via the SAME long-polling loop telegram_commands.py already runs for
/status etc. (this is the first callback_query handling anywhere in this
codebase; every previous incoming update was a plain /command message).

Storage: config.load_persistent (the same pattern this batch's other
small settings-shaped stores use) rather than a new SQL table -- reaction
counts are a lightweight, append-only-ish log, not something needing
relational queries.
"""

from datetime import datetime, timezone

from data_engine import config as base_config

_CLOUD_KEY = "signal_reactions"
_FILE = "signal_reactions.json"
_DEFAULTS = {"reactions": []}

REACTION_UP = "up"
REACTION_DOWN = "down"

_CALLBACK_PREFIX = "react"


def build_reaction_keyboard(position_id):
    """Telegram Bot API inline-keyboard shape for _raw_send's reply_markup."""
    return {
        "inline_keyboard": [[
            {"text": "\U0001F44D", "callback_data": f"{_CALLBACK_PREFIX}:{REACTION_UP}:{position_id}"},
            {"text": "\U0001F44E", "callback_data": f"{_CALLBACK_PREFIX}:{REACTION_DOWN}:{position_id}"},
        ]]
    }


def parse_reaction_callback(callback_data):
    """Returns (reaction, position_id), or None if this callback_data
    isn't one of ours (e.g. some other future button type) -- never
    raises on unexpected input."""
    if not callback_data or not callback_data.startswith(f"{_CALLBACK_PREFIX}:"):
        return None
    parts = callback_data.split(":", 2)
    if len(parts) != 3 or parts[1] not in (REACTION_UP, REACTION_DOWN):
        return None
    return parts[1], parts[2]


def record_reaction(position_id, reaction, from_user=None, now_iso=None):
    if reaction not in (REACTION_UP, REACTION_DOWN):
        raise ValueError(f"unknown reaction: {reaction}")
    data = base_config.load_persistent(_CLOUD_KEY, _FILE, _DEFAULTS)
    data["reactions"].append({
        "position_id": position_id, "reaction": reaction, "from_user": from_user,
        "at": now_iso or datetime.now(timezone.utc).isoformat(),
    })
    base_config.save_persistent(_CLOUD_KEY, _FILE, data)


def list_reactions(position_id=None):
    reactions = base_config.load_persistent(_CLOUD_KEY, _FILE, _DEFAULTS)["reactions"]
    if position_id:
        reactions = [r for r in reactions if r["position_id"] == position_id]
    return reactions


def reaction_counts(position_id):
    rows = list_reactions(position_id)
    return {
        "up": sum(1 for r in rows if r["reaction"] == REACTION_UP),
        "down": sum(1 for r in rows if r["reaction"] == REACTION_DOWN),
    }
