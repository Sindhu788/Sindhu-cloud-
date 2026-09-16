"""Confidence Score -- calculated purely for reporting/ranking/priority
tie-breaking. Per spec: confidence NEVER blocks a valid trade; the Risk
Manager is the only gate that can reject one.

2026-09-17 fix (Investigation Batch, 1.1): real evidence showed this was
badly miscalibrated -- a sample of the last 50 real trades stated ~75.8%
average confidence but had only an 18% real win rate. Root cause: the
heuristic in _raw_score() below was never fit to real outcomes at all,
just hand-picked point values (a 50 base, a lesson-influence nudge, a
strategy-version bonus, a trend-alignment bonus/penalty, ...) -- a
reasonable relative ranking signal, but never a probability, and nothing
here ever checked it against what actually happened.

Fix: score() now runs the same raw heuristic, then looks up its 10%-wide
bucket in paper_trading.confidence_calibration's real calibration map
(built purely from real closed paper trades, same 25-trade "enough
evidence" bar the Wilson gate uses elsewhere). Once a bucket has enough
real history, score() returns the REAL win rate for that bucket instead
of the raw number -- so a displayed "75%" then means "of past signals
scored like this one, about 75% actually won", not an arbitrary
formula's opinion. A bucket without 25 real trades yet has no honest
calibrated number to give, so score() falls back to the raw heuristic
unchanged -- never fabricates a calibrated number from too little
evidence. See confidence_calibration.py's own docstring for the caching
this relies on to stay cheap when called once per candidate per scan.
"""

from data_engine import storage
from paper_trading import confidence_calibration, lesson_auto_apply


def score(candidate, market_snapshot):
    raw = _raw_score(candidate, market_snapshot)
    calibrated, trustworthy, _sample_size = confidence_calibration.calibrated_win_rate_for(
        raw, use_cache=True,
    )
    return calibrated if trustworthy else raw


def _raw_score(candidate, market_snapshot):
    value = 50.0

    # Lesson Auto-Apply (Self-Learning Group, item 2): a SOFT nudge only --
    # bounded at +/-10 points out of 100, never enough alone to flip a
    # candidate between approved/rejected (confidence never gates a trade,
    # per this module's own docstring; Risk Manager is the only real gate).
    value += lesson_auto_apply.get_influence(
        candidate.get("strategy_id"), market_snapshot.get("symbol"),
        market_snapshot.get("market_state"), market_snapshot.get("session"),
    )

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
