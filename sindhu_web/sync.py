"""Central hook for real-time synchronization. Every mutating API endpoint
(strategies, lessons, settings) should call notify() instead of touching
broadcast.publish directly -- it both records the change in the Activity
Feed (data/database, activity_log table) and pushes it live to every
connected device over the WebSocket, so Desktop and Mobile stay in sync
without a manual refresh.

Grand Feature Expansion, Phase 1 Feature 3: every notify() call is also
permanently recorded to audit_trail_log (data_engine.storage.record_audit_event)
-- unlike activity_log, that table is never pruned. notify() is already the
codebase's single choke point for "significant, worth telling the user
about" events (~50 call sites: strategy/lesson/settings/paper-trading/
engine-on-off changes), so piggy-backing here gives the audit trail broad
coverage for free rather than requiring every call site to be found and
edited individually."""

from datetime import datetime, timezone

from data_engine import storage
from sindhu_web import broadcast


def notify(entity, action, message, **extra):
    now = datetime.now(timezone.utc).isoformat()
    storage.log_activity(entity, action, message, now)
    storage.record_audit_event(entity, action, message, now)
    broadcast.publish({
        "channel": "sync",
        "entity": entity,
        "action": action,
        "message": message,
        "at": now,
        **extra,
    })
