"""The Knowledge Engine: checks CEO-authored lessons before every trade,
alongside the strategy itself. Loaded once per backtest run from active
lessons flagged for the current context (backtesting / paper trading /
evolution); each check is logged to lesson_applications so lesson
statistics and the Knowledge Score stay accurate.
"""

from datetime import datetime, timezone

from data_engine import storage
from knowledge_engine.lesson import from_storage_dict
from knowledge_engine.condition_eval import evaluate_condition

_PRIORITY_RANK = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


class KnowledgeEngine:
    def __init__(self, lessons=None, batch_id=None, symbol=None, timeframe=None, log_fn=None):
        self.lessons = sorted(lessons or [], key=lambda l: -_PRIORITY_RANK.get(l.priority, 2))
        self.batch_id = batch_id
        self.symbol = symbol
        self.timeframe = timeframe
        self.log_fn = log_fn
        # check() is called on every bar a strategy signal fires (Phase 4);
        # writing each lesson outcome straight to SQLite there was the
        # single biggest per-bar cost in the whole backtest. Buffered in
        # memory here instead and flushed in one bulk write -- see flush().
        self._pending_applications = []
        # Per-symbol-backtest cache of column -> numpy array, reused across
        # every check() call against the same df (fresh per instance, and a
        # new KnowledgeEngine is created per symbol) -- see condition_eval's
        # evaluate_condition() docstring for why this avoids re-slicing a
        # pandas Series on every bar.
        self._arr_cache = {}

    @classmethod
    def for_backtesting(cls, batch_id=None, symbol=None, timeframe=None, log_fn=None):
        rows = storage.list_lessons(status="active", apply_backtesting=True)
        lessons = [from_storage_dict(r) for r in rows]
        return cls(lessons, batch_id=batch_id, symbol=symbol, timeframe=timeframe, log_fn=log_fn)

    @classmethod
    def for_paper_trading(cls, symbol=None, timeframe=None, market_type=None, log_fn=None):
        """Same active-lesson gating as backtesting, filtered to lessons
        flagged for Paper Trading and (optionally) the current coin's
        market type / timeframe -- Lesson.matches_market_type/timeframe
        default to "matches everything" when a lesson doesn't restrict
        itself, so existing lessons keep working unchanged."""
        rows = storage.list_lessons(status="active")
        lessons = [from_storage_dict(r) for r in rows if r.get("apply_paper_trading")]
        if market_type:
            lessons = [l for l in lessons if l.matches_market_type(market_type)]
        if timeframe:
            lessons = [l for l in lessons if l.matches_timeframe(timeframe)]
        return cls(lessons, batch_id=None, symbol=symbol, timeframe=timeframe, log_fn=log_fn)

    def has_active_lessons(self):
        return any(l.is_enforceable() for l in self.lessons)

    def check(self, df, i, direction):
        """Called once per prospective trade entry (strategy already said
        "buy"/"sell"). Returns (approved: bool, reason: str|None). Every
        enforceable lesson evaluated gets logged as approved or rejected,
        highest priority first; the first lesson that blocks wins and
        stops further checks."""
        now_iso = _now_iso()
        for lesson in self.lessons:
            if not lesson.is_enforceable():
                continue
            if lesson.direction and lesson.direction != direction:
                continue

            condition_true = all(evaluate_condition(df, i, c, self._arr_cache) for c in lesson.conditions)
            triggered = condition_true if lesson.rule_type == "block_if_true" else not condition_true

            outcome = "rejected" if triggered else "approved"
            self._pending_applications.append(
                (lesson.id, self.batch_id, self.symbol, self.timeframe, now_iso, outcome)
            )

            if triggered:
                reason = f"{lesson.title} ({lesson.category})"
                if self.log_fn:
                    self.log_fn(f"  Trade blocked by lesson: {reason}")
                return False, reason

        return True, None

    def flush(self):
        """Writes every lesson application accumulated since the last flush
        in a single bulk INSERT. Call once per symbol after a backtest run
        finishes (and in a finally/except so partial progress is never
        lost if the run fails partway through)."""
        if not self._pending_applications:
            return
        storage.record_lesson_applications_bulk(self._pending_applications)
        self._pending_applications = []
