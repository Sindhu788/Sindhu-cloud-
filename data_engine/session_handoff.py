"""Session Handoff Auto-Summary (Grand Feature Expansion, Phase 4 Feature
20): a narrative "what happened / what's next" handoff note. Genuinely
distinct from what_changed.summarize_period() (raw audit-trail event
COUNTS, e.g. "incident was created 2 times") -- this turns those same
counts into readable prose for the "what happened" half, then adds a
"what's next" half built from LIVE current state (not history), reusing
the exact same safety/attention sources Today's Focus Widget (Phase 4
Feature 19) already reads on the frontend."""

from datetime import datetime, timezone

from data_engine import storage, what_changed
from paper_trading import account_drawdown_guard, graveyard, kill_switch


def generate_handoff_summary(since_iso):
    changed = what_changed.summarize_period(since_iso)

    if changed["total_events"] == 0:
        happened_line = "Nothing was recorded in the permanent audit trail for this period."
    else:
        happened_line = "What happened: " + "; ".join(changed["summary_lines"]) + "."

    next_up = []
    ks = kill_switch.status()
    if ks["active"]:
        next_up.append(f"the kill switch is still ACTIVE ({ks.get('reason') or 'no reason given'}) -- decide whether to deactivate it")
    dd = account_drawdown_guard.status()
    if dd["paused"]:
        next_up.append(f"account-wide drawdown protection is still paused ({dd.get('paused_reason') or 'no reason given'})")
    open_incidents = storage.list_incidents(status="open")
    if open_incidents:
        count = len(open_incidents)
        next_up.append(f"{count} incident{'s' if count != 1 else ''} still open")
    suggestions = graveyard.compute_retirement_suggestions()
    if suggestions:
        count = len(suggestions)
        next_up.append(f"{count} strategy retirement suggestion{'s' if count != 1 else ''} waiting for a decision")

    next_line = ("What's next: " + "; ".join(next_up) + ".") if next_up \
        else "What's next: nothing urgent waiting -- a good place to stop."

    text = happened_line + "\n\n" + next_line
    return {
        "since": since_iso,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "text": text,
        "total_events": changed["total_events"],
        "next_up_count": len(next_up),
    }
