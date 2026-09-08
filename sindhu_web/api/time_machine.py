"""Grand Master Prompt, Phase 4.5: Time Machine -- pick a past date, see
what the audit trail (a permanent, never-pruned event log) recorded that
day, plus whatever weekly snapshot is closest to that date if one exists.

Honest scope: this does NOT reconstruct full system state as of that date
(e.g. "what was every strategy's win rate on that day") -- the codebase
has no such point-in-time state store. It surfaces what genuinely IS
recorded with a timestamp (audit_trail_log events, and the nearest weekly
snapshot's own file), and says so plainly rather than fabricating a full
historical snapshot.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException

from data_engine import storage

router = APIRouter()


@router.get("/api/time-machine/{date_str}")
def get_time_machine(date_str: str):
    try:
        day = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(400, "date must be in YYYY-MM-DD format")

    since_iso = day.isoformat()
    until_iso = (day + timedelta(days=1)).isoformat()
    events = storage.list_audit_trail_between(since_iso, until_iso)

    from sindhu_web.api.weekly_snapshot import list_weekly_snapshots
    snapshots = list_weekly_snapshots()
    nearest_snapshot = None
    if snapshots:
        nearest_snapshot = min(
            snapshots,
            key=lambda s: abs((datetime.fromisoformat(s["modified_at"]) - day).total_seconds()),
        )

    return {
        "date": date_str,
        "events": events,
        "event_count": len(events),
        "nearest_weekly_snapshot": nearest_snapshot,
        "note": ("This shows real permanent audit-trail events recorded on this date, plus the "
                 "closest available weekly database snapshot. It does NOT reconstruct full system "
                 "state as of this date (e.g. every strategy's exact numbers that day) -- no such "
                 "point-in-time record exists in this codebase."),
    }
