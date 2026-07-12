"""Evolution (Paper Trading scope): uses Reflection's outcome only to keep
Strategy/Lesson rankings, scores, and confidence inputs up to date. It
never modifies the original strategy or lesson content -- that stays
entirely CEO-authored. A future, full Evolution phase can build
suggestions on top of these numbers; this module only maintains them.
"""

from datetime import datetime, timezone

from data_engine import storage


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def record_outcome(position, pnl, pnl_pct):
    is_win = pnl > 0
    now = _now_iso()

    if position.get("strategy_id"):
        rr = abs(pnl_pct) if is_win else None
        storage.update_paper_strategy_performance(
            position["strategy_id"], position.get("strategy_name"), pnl, is_win, rr, now,
        )

    for lesson_id in position.get("lesson_ids", []) or []:
        lesson = storage.get_lesson(lesson_id)
        title = lesson["title"] if lesson else lesson_id
        storage.update_paper_lesson_performance(
            lesson_id, title, pnl, is_win, position.get("confidence"), now,
        )
