"""Phase 1 -- channel management. Multiple channels supported from the
start (never a single-channel assumption): add/name/enable/disable/
remove, each with its own stable forwarding source label.
"""

import uuid
from datetime import datetime, timezone

from data_engine import storage
from external_signals.forwarder import _next_source_label


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def add_channel(name, telegram_identifier):
    if not name or not name.strip():
        raise ValueError("Channel name is required.")
    if not telegram_identifier or not telegram_identifier.strip():
        raise ValueError("Telegram username/id is required.")
    channel_id = uuid.uuid4().hex[:12]
    label = _next_source_label()
    now = _now_iso()
    storage.save_external_channel(channel_id, name.strip(), telegram_identifier.strip(), label, now)
    return channel_id


def list_channels():
    return storage.list_external_channels()


def set_enabled(channel_id, enabled):
    storage.set_external_channel_enabled(channel_id, enabled, _now_iso())


def rename(channel_id, new_name):
    if not new_name or not new_name.strip():
        raise ValueError("Channel name is required.")
    storage.rename_external_channel(channel_id, new_name.strip(), _now_iso())


def remove(channel_id):
    """Removes the CHANNEL row only -- every message/signal/position it
    ever produced is kept forever (standing no-deletion rule), see
    data_engine.storage.delete_external_channel."""
    storage.delete_external_channel(channel_id)
