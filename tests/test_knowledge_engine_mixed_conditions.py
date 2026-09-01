"""Full A-to-Z audit, Phase 4: KnowledgeEngine.check() evaluated ALL of a
lesson's conditions with all(), including non-dispatchable ones (a "raw"
condition, or a bare/unrecognized "concept" name) which evaluate_condition()
always resolves to False. Lesson.is_enforceable() was already fixed
(any(condition_is_executable(...))) to stop an ALL-broken lesson from
silently vetoing every trade forever -- but that fix never reached check(),
so a lesson with a MIX of one real condition and one broken one still hit
the same failure mode: require_if_true blocks every trade regardless of the
real condition (the broken one poisons all() to False -> triggered=True
always); block_if_true silently never enforces (poisoned to False ->
triggered=False always). Fixed by filtering to dispatchable conditions in
check(), mirroring is_enforceable()'s own logic.
"""

import pandas as pd

from backtest_engine.strategy_config import Condition
from knowledge_engine.engine import KnowledgeEngine
from knowledge_engine.lesson import Lesson


def _df():
    return pd.DataFrame({"entry_session": ["london"], "close": [100.0]})


def _mixed_lesson(rule_type):
    return Lesson(
        id="l1", title="Mixed condition lesson", category="Other",
        rule_type=rule_type, direction="bullish",
        conditions=[
            Condition(type="concept", name="sma"),  # bare/unrecognized -- not dispatchable
            Condition(type="session", name="london"),  # real, true on the test df
        ],
    )


def test_broken_plus_true_condition_is_enforceable():
    lesson = _mixed_lesson("require_if_true")
    assert lesson.is_enforceable() is True  # has at least one dispatchable condition


def test_require_if_true_mixed_lesson_approves_when_real_condition_is_true():
    """Before the fix: the broken 'sma' condition poisoned all() to False,
    so 'not condition_true' was always True -- blocking every trade
    regardless of the real condition. After the fix: only the real
    dispatchable condition (session == london, true here) is evaluated."""
    engine = KnowledgeEngine(lessons=[_mixed_lesson("require_if_true")])
    approved, reason = engine.check(_df(), 0, "bullish")
    assert approved is True
    assert reason is None


def test_require_if_true_mixed_lesson_blocks_when_real_condition_is_false():
    lesson = _mixed_lesson("require_if_true")
    lesson.conditions[1] = Condition(type="session", name="new_york")  # real condition now false
    engine = KnowledgeEngine(lessons=[lesson])
    approved, reason = engine.check(_df(), 0, "bullish")
    assert approved is False
    assert reason is not None


def test_block_if_true_mixed_lesson_blocks_when_real_condition_is_true():
    """Before the fix: the broken 'sma' condition poisoned all() to False,
    so block_if_true's trigger (condition_true) was always False --
    silently never enforcing this lesson no matter what. After the fix:
    the real condition (true here) correctly triggers the block."""
    engine = KnowledgeEngine(lessons=[_mixed_lesson("block_if_true")])
    approved, reason = engine.check(_df(), 0, "bullish")
    assert approved is False
    assert reason is not None


def test_block_if_true_mixed_lesson_approves_when_real_condition_is_false():
    lesson = _mixed_lesson("block_if_true")
    lesson.conditions[1] = Condition(type="session", name="new_york")
    engine = KnowledgeEngine(lessons=[lesson])
    approved, reason = engine.check(_df(), 0, "bullish")
    assert approved is True
