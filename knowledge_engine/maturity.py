"""System Maturity Level: a real Level 1-5 indicator computed entirely from
data the system already has -- never manually set, never rounded up.
Recomputed fresh on every call (a live snapshot, not a permanent
achievement record), so if a strategy's edge disappears or trades reset,
the level honestly reflects that. Each level's requirement builds on the
one before it (a genuine ladder, not five independent checks), matching
what the CEO asked for: how many strategies have completed meaningful
numbers of trades, how many have passed the 100-trade Evolution gate,
whether any have a statistically sustained positive result, and whether
signals are actually being delivered.

Deliberately reads existing gates read-only (paper_trading.pattern_stats'
25-trade Wilson classification, evolution_engine's 100-trade comparison
records) -- never touches or duplicates their logic.
"""

from datetime import datetime, timezone, timedelta

from data_engine import storage
from paper_trading import pattern_stats

SIGNAL_FRESHNESS_DAYS = 7


def _real_strategy_books():
    # paper_account_state has one synthetic "__lessons__" row for trades
    # not tied to any specific strategy -- not a real strategy, excluded.
    return [s for s in storage.list_paper_account_states() if s["strategy_id"] != "__lessons__"]


def _evolution_gate_completions(min_threshold=100):
    """Strategies whose self-learning loop has actually finished judging a
    mutation against the 100-trade gate (verdict recorded -- "improved" or
    "regressed", win or lose) -- not just started one."""
    with storage.get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(DISTINCT base_id) FROM evolution_comparisons "
            "WHERE trade_threshold >= ? AND verdict IS NOT NULL",
            (min_threshold,),
        ).fetchone()
    return row[0] or 0


def compute_maturity_metrics():
    """The real numbers behind the level -- shown alongside it so the CEO
    never has to take the level on faith."""
    books = _real_strategy_books()
    with_25plus = [b for b in books if b["closed_count"] >= 25]
    proven_positive = [
        b for b in with_25plus
        if pattern_stats.classify(wins=b["win_count"], n=b["closed_count"])["status"] == "reliable_good"
    ]
    since = (datetime.now(timezone.utc) - timedelta(days=SIGNAL_FRESHNESS_DAYS)).isoformat()
    return {
        "total_strategy_books": len(books),
        "strategies_with_25plus_trades": len(with_25plus),
        "strategies_statistically_proven_positive": len(proven_positive),
        "evolution_gate_completions": _evolution_gate_completions(),
        "ever_sent_a_signal": storage.get_last_telegram_signal_sent_at() is not None,
        "signals_sent_last_7_days": storage.count_telegram_messages_since(since),
    }


LEVEL_NAMES = {
    1: "Bootstrapping",
    2: "Data Collecting",
    3: "Self-Learning Active",
    4: "Proven Edge",
    5: "Fully Validated",
}

# Roman Urdu, plain-language -- what EACH level (on its own, not cumulative
# wording) actually requires, shown to the CEO next to the current level.
LEVEL_CRITERIA_TEXT = {
    1: "System shuru ho chuka hai aur strategies import ho chuki hain -- lekin abhi tak koi strategy ne 25 real paper trades poori nahi ki.",
    2: "Kam se kam 1 strategy ne 25+ real paper trades poori kar li hain -- ab ussey kaafi data hai reliability judge karne ke liye.",
    3: "Kam se kam 1 strategy Evolution ke 100-trade gate se guzar chuki hai (chahe result improve ho ya rollback) -- self-learning loop asal mein chal raha hai.",
    4: "Kam se kam 1 strategy ka win rate 25+ trades par statistically confirm ho chuka hai (sirf luck nahi), aur Telegram par kam se kam ek real signal bheja ja chuka hai.",
    5: "Kam se kam 2 strategies ka win rate statistically confirm ho chuka hai, aur pichle 7 dinon mein Telegram signals bhi bheje ja rahe hain.",
}


def _ladder(metrics):
    l2 = metrics["strategies_with_25plus_trades"] >= 1
    l3 = l2 and metrics["evolution_gate_completions"] >= 1
    l4 = l3 and metrics["strategies_statistically_proven_positive"] >= 1 and metrics["ever_sent_a_signal"]
    l5 = l4 and metrics["strategies_statistically_proven_positive"] >= 2 and metrics["signals_sent_last_7_days"] >= 1
    return {2: l2, 3: l3, 4: l4, 5: l5}


def compute_maturity_level(metrics=None):
    if metrics is None:
        metrics = compute_maturity_metrics()
    met = _ladder(metrics)
    level = 5 if met[5] else 4 if met[4] else 3 if met[3] else 2 if met[2] else 1
    next_level = level + 1 if level < 5 else None
    return {
        "level": level,
        "level_name": LEVEL_NAMES[level],
        "criteria_text": LEVEL_CRITERIA_TEXT[level],
        "next_level": next_level,
        "next_level_name": LEVEL_NAMES.get(next_level),
        "next_level_criteria_text": LEVEL_CRITERIA_TEXT.get(next_level),
        "metrics": metrics,
    }
