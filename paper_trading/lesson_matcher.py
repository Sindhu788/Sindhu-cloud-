"""Lesson Engine: lessons are completely independent of strategies and of
each other. A lesson is relevant to a coin/tick when it's active, flagged
for Paper Trading, and (if it restricts itself) matches the current
market state / timeframe -- exactly the same "empty means unrestricted"
convention strategies use, so existing lessons keep applying everywhere
unless the CEO deliberately narrows them.
"""

from data_engine import storage
from knowledge_engine.lesson import from_storage_dict


def relevant_lessons(market_state, timeframe):
    rows = storage.list_lessons(status="active")
    lessons = [from_storage_dict(r) for r in rows if r.get("apply_paper_trading")]
    lessons = [l for l in lessons if l.matches_market_type(market_state) and l.matches_timeframe(timeframe)]
    lessons = [l for l in lessons if l.is_enforceable()]
    priority_rank = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}
    lessons.sort(key=lambda l: -priority_rank.get(l.priority, 2))
    return lessons
