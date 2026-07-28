"""Lesson Auto-Apply System (Self-Learning Group, item 2; strengthened to a
statistical gate in the Genuine Evolution Engine pass): the next step
after Lesson Candidate flagging (paper_trading.insights.detect_lesson_candidates,
which only ever writes to paper_lesson_candidates for a PERSON to review).
Once a pattern's full trade history clears pattern_stats' statistical
reliability gate (Wilson score interval, minimum 25 trades -- see
paper_trading.pattern_stats), it's promoted here into an ACTIVE rule that
nudges confidence for future matching candidates -- a soft filter (see
paper_trading.confidence), never a hard block, and always visible +
reversible from the dashboard (paper_auto_lessons, `active` flag).

Previously this triggered off just 10 trades at an 80%+ one-sided split,
which a real strategy can clear from short-run luck alone. It now shares
the exact same statistical classification pattern_stats.auto_avoid uses:
below 25 trades for that exact pattern, nothing is promoted regardless of
how extreme the raw win rate looks ("insufficient data -- observing");
at or above 25, a pattern is only promoted once the Wilson 95% confidence
interval is confidently on one side of 50%.
"""

from datetime import datetime, timezone

from data_engine import storage
from paper_trading import insights, pattern_stats

CONFIDENCE_NUDGE = 10.0  # soft -- never enough alone to flip approved/rejected


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def promote_candidates():
    """Scans Coin-Specific Pattern Memory (fresh session only) for patterns
    that clear pattern_stats' statistical reliability gate and promotes
    each into an active paper_auto_lessons row -- or deactivates a
    previously-promoted row whose pattern has since drifted back to
    inconclusive. Idempotent -- re-running just refreshes the same row's
    evidence (sample_size/win_rate) via the UNIQUE constraint's ON
    CONFLICT upsert. Returns the list of newly-promoted (or refreshed)
    explanations for this call, for logging."""
    patterns = storage.list_paper_coin_pattern_memory(since=insights.fresh_session_start())
    now = _now_iso()
    promoted = []
    still_reliable = set()

    for p in patterns:
        result = pattern_stats.classify(p["wins"], p["trades"])
        key = (p["strategy_id"], p["symbol"], p["market_state"], p["session"])
        if result["status"] not in ("reliable_good", "reliable_bad"):
            continue
        still_reliable.add(key)

        influence = "boost" if result["status"] == "reliable_good" else "avoid"
        verb = "wins" if influence == "boost" else "loses"
        explanation = (
            f"{p['strategy_name'] or p['strategy_id']} statistically {verb} on {p['symbol']} "
            f"during {p['market_state']} markets in the {p['session']} session "
            f"({result['win_rate_pct']:.0f}% win rate over {result['sample_size']} trades, "
            f"95% CI {result['ci_lower_pct']:.0f}%-{result['ci_upper_pct']:.0f}%). "
            f"Future signals matching this exact situation get a "
            f"{'small confidence boost' if influence == 'boost' else 'small confidence reduction'} "
            f"-- this never blocks a trade by itself."
        )
        storage.save_paper_auto_lesson(
            p["strategy_id"], p["strategy_name"], p["symbol"], p["market_state"], p["session"],
            influence, result["sample_size"], result["win_rate_pct"], explanation, now,
        )
        promoted.append(explanation)

    # A pattern that WAS reliable and promoted, but has since drifted back
    # to inconclusive (more mixed results came in), should stop influencing
    # confidence -- deactivate rather than leave a stale conclusion active.
    for row in storage.list_paper_auto_lessons(active_only=True):
        key = (row["strategy_id"], row["symbol"], row["market_state"], row["session"])
        if key not in still_reliable:
            storage.deactivate_paper_auto_lesson(row["id"], now)

    return promoted


def get_influence(strategy_id, symbol, market_state, session):
    """Returns +CONFIDENCE_NUDGE, -CONFIDENCE_NUDGE, or 0.0 -- called from
    paper_trading.confidence.score(). Degrades gracefully: a candidate with
    no strategy_id, or a pattern with no active auto-lesson, contributes 0."""
    if not strategy_id or not symbol or not market_state or not session:
        return 0.0
    row = storage.get_paper_auto_lesson(strategy_id, symbol, market_state, session)
    if not row:
        return 0.0
    return CONFIDENCE_NUDGE if row["influence"] == "boost" else -CONFIDENCE_NUDGE
