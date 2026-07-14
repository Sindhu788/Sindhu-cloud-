"""Knowledge Score: a simple, transparent, documented formula -- not AI,
just arithmetic over what's already tracked. Starts at 0% and rises as
lessons are added, activated, and successfully applied in real backtests.
"""

from data_engine import storage

_POINTS_PER_LESSON = 2
_POINTS_PER_ACTIVE_LESSON = 3
_POINTS_PER_APPROVED_APPLICATION = 0.1


def compute_knowledge_score(report=None):
    if report is None:
        report = storage.get_knowledge_report()
    score = (
        report["total_lessons"] * _POINTS_PER_LESSON
        + report["active_lessons"] * _POINTS_PER_ACTIVE_LESSON
        + report["trades_approved_by_lessons"] * _POINTS_PER_APPROVED_APPLICATION
    )
    return min(100.0, round(score, 1))


_EMPTY_STATS = {"times_used": 0, "trades_approved": 0, "trades_rejected": 0}


def _impact_pct_from_stats(stats):
    """% of checks where this lesson actually changed the outcome (blocked
    a trade) -- a lesson that's never rejected anything has zero impact,
    regardless of how often it was checked. Shared by lesson_estimated_impact()
    and list_lessons_with_stats() so both compute it identically."""
    times_used = stats["times_used"]
    if times_used == 0:
        return 0.0
    return round(stats["trades_rejected"] / times_used * 100, 1)


def lesson_estimated_impact(lesson_id):
    return _impact_pct_from_stats(storage.get_lesson_stats(lesson_id))


def list_lessons_with_stats(status=None, category=None):
    """Performance note: this used to call storage.get_lesson_stats() twice
    per lesson (once directly, once inside lesson_estimated_impact()) --
    with lesson_applications at 3.6M rows and no index, that was 220
    separate near-full-table scans on every page load (90+ seconds
    measured). storage.get_lesson_stats_bulk() below fetches every lesson's
    stats in a single grouped query instead, then _impact_pct_from_stats()
    reuses that same in-memory result rather than re-querying. Same formula,
    same results -- just computed once per lesson instead of twice, and
    fetched in one query instead of per-lesson round trips."""
    lessons = storage.list_lessons(status=status, category=category)
    stats_by_id = storage.get_lesson_stats_bulk([lesson["id"] for lesson in lessons])
    for lesson in lessons:
        stats = stats_by_id.get(lesson["id"], _EMPTY_STATS)
        lesson["stats"] = stats
        lesson["estimated_impact_pct"] = _impact_pct_from_stats(stats)
    return lessons
