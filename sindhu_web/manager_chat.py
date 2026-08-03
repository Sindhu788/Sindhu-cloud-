"""Manager Chat (Batch 4, Task 6): a deterministic, keyword-matched
question-and-answer panel over real database data. No AI, no LLM calls,
no machine learning -- every answer is built from an exact function call
against real stored numbers, so it costs nothing to run and can never
fabricate a figure. Strictly read-only: every function this module calls
is a storage/domain read, never a write -- see test_manager_chat.py's
test_no_handler_ever_calls_a_write_function for the guarantee this holds.

Answers are returned in Roman Urdu or English depending on `lang`,
respecting the Task 4 language toggle. An unrecognized question returns
a plain "I didn't understand" response listing what CAN be asked --
never a guess.
"""

from datetime import datetime, timezone, timedelta

from data_engine import storage
from paper_trading.engine import engine as paper_engine
from paper_trading import config as pt_config
from backtest_engine import strategy_library as lib
from ai_integration import extraction_lock
from knowledge_engine.maturity import compute_maturity_level


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _today_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# --------------------------------------------------------------- answer builders (all read-only)

def _answer_best_strategy(lang):
    states = [s for s in storage.list_paper_account_states() if s["strategy_id"] != "__lessons__"]
    candidates = [s for s in states if s["closed_count"] >= 5]  # a handful of trades at least, not a fluke on 1
    if not candidates:
        return ("Abhi kisi bhi strategy ke paas itni trades nahi hain ke 'best' bataya ja sake."
                if lang == "ur" else
                "No strategy has enough closed trades yet to call one the best.")
    best = max(candidates, key=lambda s: s["realized_pnl_total"])
    win_rate = round(best["win_count"] / best["closed_count"] * 100, 1) if best["closed_count"] else 0.0
    name = _strategy_name(best["strategy_id"])
    if lang == "ur":
        return (f"Abhi sabse behtar chal rahi strategy hai: {name} -- "
                f"${best['realized_pnl_total']:.2f} munafa, {best['closed_count']} trades, "
                f"{win_rate}% jeetne ki dar.")
    return (f"The best-performing strategy right now is: {name} -- "
            f"${best['realized_pnl_total']:.2f} profit, {best['closed_count']} trades, "
            f"{win_rate}% win rate.")


def _strategy_name(strategy_id):
    try:
        return lib.load(strategy_id).name
    except FileNotFoundError:
        return strategy_id


def _answer_today(lang):
    today = _today_str()
    trades = storage.list_paper_closed_trades_ordered(limit=5000)
    todays_trades = [t for t in trades if (t["closed_at"] or "").startswith(today)]
    wins = sum(1 for t in todays_trades if (t["pnl"] or 0) > 0)
    total_pnl = sum(t["pnl"] or 0 for t in todays_trades)
    since_midnight = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00")
    signals_today = storage.count_telegram_messages_since(since_midnight)
    if lang == "ur":
        return (f"Aaj tak: {len(todays_trades)} trades band hui ({wins} jeeti), "
                f"total result ${total_pnl:.2f}, aur {signals_today} signals Telegram par bheje gaye.")
    return (f"Today so far: {len(todays_trades)} trades closed ({wins} wins), "
            f"total result ${total_pnl:.2f}, and {signals_today} signals sent to Telegram.")


def _answer_signals_recent(lang):
    since_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    count_24h = storage.count_telegram_messages_since(since_24h)
    last_sent = storage.get_last_telegram_signal_sent_at()
    if lang == "ur":
        last_text = f"Aakhri signal {last_sent[:16].replace('T', ' ')} UTC par bheja gaya tha." if last_sent else "Abhi tak koi signal nahi bheja gaya."
        return f"Pichle 24 ghanton mein {count_24h} signals Telegram par bheje gaye. {last_text}"
    last_text = f"The last signal was sent at {last_sent[:16].replace('T', ' ')} UTC." if last_sent else "No signal has ever been sent yet."
    return f"{count_24h} signals were sent to Telegram in the last 24 hours. {last_text}"


def _answer_balance_pnl(lang):
    status = paper_engine.status()
    settings = pt_config.load()
    initial = settings.get("initial_balance", 10000.0)
    combined_initial = initial * len(status["per_strategy"])
    pnl = status["balance"] - combined_initial
    pnl_pct = (pnl / combined_initial * 100) if combined_initial else 0.0
    if lang == "ur":
        return (f"Abhi combined balance ${status['balance']:.2f} hai "
                f"({pnl >= 0 and '+' or ''}{pnl:.2f} = {pnl_pct:+.2f}% shuruaati balance se), "
                f"{len(status['per_strategy'])} strategy book(s) milakar.")
    return (f"Combined balance right now is ${status['balance']:.2f} "
            f"({pnl:+.2f} = {pnl_pct:+.2f}% from the starting balance), "
            f"across {len(status['per_strategy'])} strategy book(s).")


def _answer_locked_strategies(lang):
    metas = [m for m in lib.list_all() if not m.get("archived")]
    lock_statuses = extraction_lock.check_strategy_locks_bulk([m["id"] for m in metas])
    locked = [m for m in metas if lock_statuses.get(m["id"], {}).get("locked")]
    if not locked:
        return ("Abhi koi bhi strategy locked/incomplete nahi hai." if lang == "ur"
                else "No strategies are currently locked or incomplete.")
    names = ", ".join(m["name"] for m in locked[:10])
    more = f" (+{len(locked) - 10} more)" if len(locked) > 10 else ""
    if lang == "ur":
        return f"{len(locked)} strategies abhi locked/incomplete hain (kuch rules samajh nahi aaye): {names}{more}."
    return f"{len(locked)} strategies are currently locked/incomplete (some rules weren't understood): {names}{more}."


def _answer_maturity(lang):
    result = compute_maturity_level()
    if lang == "ur":
        return f"System abhi Level {result['level']}/5 par hai -- {result['criteria_text']}"
    en_names = {
        1: "Bootstrapping", 2: "Data Collecting", 3: "Self-Learning Active",
        4: "Proven Edge", 5: "Fully Validated",
    }
    return f"The system is currently at Level {result['level']}/5 ({en_names[result['level']]})."


# --------------------------------------------------------------- intent routing

# Ordered so more specific intents (e.g. "today") are checked before more
# general ones that share a keyword (e.g. "signal" also appears in the
# today summary). First match wins.
_INTENTS = [
    # Deliberately phrase-level (not bare "today"/"aaj") to avoid false
    # positives on unrelated sentences that happen to mention the day --
    # e.g. "mausam kaisa hai aaj" (what's the weather today) is not a
    # request for trading activity.
    ("today", ["what happened today", "today's activity", "today's trades", "today's signals",
                "aaj kya hua", "aaj kya", "aaj ki activity", "aaj kitni", "aaj kitne"], _answer_today),
    ("maturity", ["maturity", "level", "mature"], _answer_maturity),
    ("locked_strategies", ["lock", "incomplete", "adhoori", "adhoora"], _answer_locked_strategies),
    ("signals_recent", ["signal"], _answer_signals_recent),
    ("best_strategy", ["best strategy", "best performing", "sabse acchi", "sabse behtar",
                        "top strategy", "acchi strategy", "which strategy"], _answer_best_strategy),
    ("balance_pnl", ["balance", "pnl", "profit", "nuksan", "munafa", "paisa"], _answer_balance_pnl),
]

_HELP_TEXT_UR = (
    "Yeh samajh nahi aaya. Aap yeh poochh sakte hain: "
    "'Sabse acchi strategy kaunsi hai?', 'Aaj kya hua?', 'Kitne signals bheje gaye?', "
    "'Balance aur PnL kya hai?', 'Kaunsi strategies locked hain?', 'System ka level kya hai?'"
)
_HELP_TEXT_EN = (
    "I didn't understand that. You can ask things like: "
    "'Which strategy is performing best?', 'What happened today?', 'How many signals were sent?', "
    "'What's the balance and PnL?', 'Which strategies are locked?', 'What's the system's maturity level?'"
)


def ask(question, lang="ur"):
    """Read-only. Returns {matched: bool, intent: str|None, answer: str}.
    Never raises for a question it doesn't recognize -- that's a normal,
    expected "not understood" response, not an error."""
    q = (question or "").strip().lower()
    if not q:
        return {"matched": False, "intent": None,
                "answer": _HELP_TEXT_UR if lang == "ur" else _HELP_TEXT_EN}
    for intent, keywords, handler in _INTENTS:
        if any(kw in q for kw in keywords):
            return {"matched": True, "intent": intent, "answer": handler(lang)}
    return {"matched": False, "intent": None,
            "answer": _HELP_TEXT_UR if lang == "ur" else _HELP_TEXT_EN}
