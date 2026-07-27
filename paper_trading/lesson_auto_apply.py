"""Lesson Auto-Apply System (Self-Learning Group, item 2): the next step
after Lesson Candidate flagging (paper_trading.insights.detect_lesson_candidates,
which only ever writes to paper_lesson_candidates for a PERSON to review).
Once a pattern has accumulated enough evidence to clear a stricter,
conservative bar, it's promoted here into an ACTIVE rule that nudges
confidence for future matching candidates -- a soft filter (see
paper_trading.confidence), never a hard block, and always visible +
reversible from the dashboard (paper_auto_lessons, `active` flag).

Why a stricter threshold than the candidate-flagging one: flagging a
pattern for a person to LOOK AT is low-stakes and should happen early
(insights.detect_lesson_candidates: 5+ trades, 75%+ one-sided). Auto-
APPLYING a pattern actually changes live trade ranking, so it deserves
more evidence first -- 10+ trades and an 80%+ one-sided win rate. This
mirrors the same "bigger action needs a stricter bar" reasoning already
used for drawdown_guard's strategy-pause threshold vs auto_avoid's
pattern-veto threshold.
"""

from datetime import datetime, timezone

from data_engine import storage
from paper_trading import insights

MIN_SAMPLE = 10
WIN_RATE_EXTREME = 80.0
CONFIDENCE_NUDGE = 10.0  # soft -- never enough alone to flip approved/rejected


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def promote_candidates(min_sample=MIN_SAMPLE, win_rate_extreme=WIN_RATE_EXTREME):
    """Scans Coin-Specific Pattern Memory (fresh session only) for patterns
    that clear the auto-apply bar and promotes each into an active
    paper_auto_lessons row. Idempotent -- re-running just refreshes the
    same row's evidence (sample_size/win_rate) via the UNIQUE constraint's
    ON CONFLICT upsert. Returns the list of newly-promoted (or refreshed)
    explanations for this call, for logging."""
    patterns = storage.list_paper_coin_pattern_memory(since=insights.fresh_session_start())
    now = _now_iso()
    promoted = []
    for p in patterns:
        if p["trades"] < min_sample:
            continue
        if not (p["win_rate"] >= win_rate_extreme or p["win_rate"] <= (100 - win_rate_extreme)):
            continue

        influence = "boost" if p["win_rate"] >= win_rate_extreme else "avoid"
        verb = "wins" if influence == "boost" else "loses"
        explanation = (
            f"{p['strategy_name'] or p['strategy_id']} consistently {verb} on {p['symbol']} "
            f"during {p['market_state']} markets in the {p['session']} session "
            f"({p['win_rate']:.0f}% win rate over {p['trades']} trades). "
            f"Future signals matching this exact situation get a {'small confidence boost' if influence == 'boost' else 'small confidence reduction'} "
            f"-- this never blocks a trade by itself."
        )
        storage.save_paper_auto_lesson(
            p["strategy_id"], p["strategy_name"], p["symbol"], p["market_state"], p["session"],
            influence, p["trades"], p["win_rate"], explanation, now,
        )
        promoted.append(explanation)
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
