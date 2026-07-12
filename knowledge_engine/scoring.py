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


def lesson_estimated_impact(lesson_id):
    """% of checks where this lesson actually changed the outcome (blocked
    a trade) -- a lesson that's never rejected anything has zero impact,
    regardless of how often it was checked."""
    stats = storage.get_lesson_stats(lesson_id)
    times_used = stats["times_used"]
    if times_used == 0:
        return 0.0
    return round(stats["trades_rejected"] / times_used * 100, 1)


def list_lessons_with_stats(status=None, category=None):
    lessons = storage.list_lessons(status=status, category=category)
    for lesson in lessons:
        stats = storage.get_lesson_stats(lesson["id"])
        lesson["stats"] = stats
        lesson["estimated_impact_pct"] = lesson_estimated_impact(lesson["id"])
    return lessons
