"""Confidence Score -- calculated purely for reporting/ranking/priority
tie-breaking. Per spec: confidence NEVER blocks a valid trade; the Risk
Manager is the only gate that can reject one.
"""

from data_engine import storage


def score(candidate, market_snapshot):
    value = 50.0

    if candidate["source"] == "strategy":
        value += min(candidate.get("strategy_version") or 5, 10) * 2
        perf = _strategy_perf(candidate["strategy_id"])
        if perf and perf["trades"] >= 5:
            value += (perf["win_rate"] - 50) * 0.3
    else:
        value += 5  # lessons are deliberately conservative signal sources
        perf = _lesson_perf(candidate["lesson_ids"][0]) if candidate.get("lesson_ids") else None
        if perf and perf["usage_count"] >= 5:
            value += (perf["win_rate"] - 50) * 0.3

    value += min(len(candidate.get("lesson_ids", [])), 5) * 2

    trend_state = market_snapshot.get("market_state")
    direction = candidate["direction"]
    if (trend_state == "trending_up" and direction == "bullish") or \
       (trend_state == "trending_down" and direction == "bearish"):
        value += 15
    elif trend_state == "ranging":
        value -= 5

    return round(max(0.0, min(100.0, value)), 2)


def _strategy_perf(strategy_id):
    for row in storage.list_paper_strategy_performance():
        if row["strategy_id"] == strategy_id:
            trades = row["trades"]
            win_rate = (row["wins"] / trades * 100) if trades else 0.0
            return {"trades": trades, "win_rate": win_rate}
    return None


def _lesson_perf(lesson_id):
    for row in storage.list_paper_lesson_performance():
        if row["lesson_id"] == lesson_id:
            usage = row["usage_count"]
            win_rate = (row["wins"] / usage * 100) if usage else 0.0
            return {"usage_count": usage, "win_rate": win_rate}
    return None
