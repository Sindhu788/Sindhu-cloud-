"""Central hook for real-time synchronization. Every mutating API endpoint
(strategies, lessons, settings) should call notify() instead of touching
broadcast.publish directly -- it both records the change in the Activity
Feed (data/database, activity_log table) and pushes it live to every
connected device over the WebSocket, so Desktop and Mobile stay in sync
without a manual refresh."""

from datetime import datetime, timezone

from data_engine import storage
from sindhu_web import broadcast


def notify(entity, action, message, **extra):
    now = datetime.now(timezone.utc).isoformat()
    storage.log_activity(entity, action, message, now)
    broadcast.publish({
        "channel": "sync",
        "entity": entity,
        "action": action,
        "message": message,
        "at": now,
        **extra,
    })
