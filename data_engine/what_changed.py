""""What Changed Today" Diff View (Grand Feature Expansion, Phase 3
Feature 15): a genuine, automatically-generated summary of what actually
happened in a period, built entirely from audit_trail_log (Phase 1
Feature 3's permanent, never-pruned record of every sync.notify() call --
strategy/lesson/settings/paper-trading/engine changes, kill switch,
backups, incidents, and more).

Distinct from sindhu_web/api/project_status.py's changelog.json, which is
a MANUALLY-curated, hand-written list of notable milestones -- this is a
real automatic diff of system activity, with zero hand-editing. Both
coexist: the changelog stays the CEO's own curated highlight reel; this
answers "what actually changed today" from the raw audit trail, honestly,
even for changes nobody thought to write down."""

from data_engine import storage


def summarize_period(since_iso, until_iso=None, limit=1000):
    """Groups every audit_trail_log entry in [since_iso, until_iso) by
    (entity, action) and turns the counts into plain-language sentences,
    busiest first. Returns total_events=0 with an empty summary on a
    genuinely quiet period -- never fabricates activity that didn't
    happen."""
    rows = storage.list_audit_trail(limit=limit, since_iso=since_iso)
    if until_iso:
        rows = [r for r in rows if r["created_at"] < until_iso]

    counts = {}
    for r in rows:
        key = (r["entity"], r["action"])
        counts[key] = counts.get(key, 0) + 1

    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    summary_lines = []
    for (entity, action), count in ranked:
        entity_label = entity.replace("_", " ")
        action_label = action.replace("_", " ")
        times = "time" if count == 1 else "times"
        summary_lines.append(f"{entity_label} was {action_label} {count} {times}")

    return {
        "since": since_iso, "until": until_iso, "total_events": len(rows),
        "summary_lines": summary_lines,
        "counts": [{"entity": e, "action": a, "count": c} for (e, a), c in ranked],
        "recent_events": rows[:20],
    }
