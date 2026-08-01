"""Batch 2, Task 1 -- the Knowledge page's "Lessons Applied"/"Trades
Rejected" counters (37,960,982, with 0 approvals) were entirely driven by
one broken lesson: a "**Philosophy:**..." note saved with a single bare
`concept: sma` condition (no operator/value -- not a real, comparable
rule) and rule_type="require_if_true". Since evaluate_condition() has no
dispatch branch for a bare "sma" concept, it silently returned False on
every bar forever, and require_if_true turns "condition never true" into
"ALWAYS block" -- so this one lesson vetoed every trade attempt across the
system's entire history, 37+ million times, with a 0% approval rate that
should have been an obvious red flag.

Fixed at the root: Lesson.is_enforceable() now requires a condition that's
actually dispatchable, not just present.
"""

from backtest_engine.strategy_config import Condition
from knowledge_engine.condition_eval import condition_is_executable, evaluate_condition
from knowledge_engine.lesson import Lesson


def _lesson(conditions, rule_type="block_if_true"):
    return Lesson(id="l1", title="Test Lesson", conditions=conditions, rule_type=rule_type)


def test_bare_unrecognized_concept_condition_is_not_executable():
    """The exact real broken condition: concept="sma" with no op/value --
    not one of the patterns evaluate_condition() actually dispatches."""
    cond = Condition(type="concept", name="sma")
    assert condition_is_executable(cond) is False


def test_raw_condition_is_not_executable():
    cond = Condition(type="raw", text="something unparsed")
    assert condition_is_executable(cond) is False


def test_recognized_concept_condition_is_executable():
    cond = Condition(type="concept", name="fvg", direction="bullish")
    assert condition_is_executable(cond) is True


def test_indicator_compare_condition_is_executable():
    cond = Condition(type="indicator_compare", indicator="rsi", op="<", value=30)
    assert condition_is_executable(cond) is True


def test_dict_shaped_condition_is_handled_same_as_dataclass():
    """Lessons loaded from storage arrive as plain dicts, not Condition
    dataclass instances -- condition_is_executable must handle both."""
    as_dict = {"type": "concept", "name": "sma", "op": None, "value": None}
    assert condition_is_executable(as_dict) is False
    as_dict_good = {"type": "concept", "name": "bos", "direction": "bullish"}
    assert condition_is_executable(as_dict_good) is True


def test_lesson_with_only_a_broken_condition_is_not_enforceable():
    """The real broken lesson, reconstructed: a bare concept:sma condition
    with require_if_true. Before the fix this was enforceable (len > 0)
    and vetoed every single trade it was ever checked against."""
    broken = _lesson([Condition(type="concept", name="sma")], rule_type="require_if_true")
    assert broken.is_enforceable() is False


def test_lesson_with_a_real_condition_stays_enforceable():
    good = _lesson([Condition(type="indicator_compare", indicator="rsi", op=">", value=70)])
    assert good.is_enforceable() is True


def test_lesson_with_mixed_conditions_is_enforceable_if_any_is_real():
    mixed = _lesson([
        Condition(type="concept", name="sma"),  # broken, ignored
        Condition(type="concept", name="fvg", direction="bearish"),  # real
    ])
    assert mixed.is_enforceable() is True


def test_display_knowledge_report_excludes_broken_lesson_stats(test_db):
    """The real-world dashboard fix: a broken (bare concept:sma,
    require_if_true) lesson's already-recorded 37M+ rejections must not
    show up in the report the Knowledge/Overview pages actually read, even
    though the raw storage totals (never deleted) still contain them."""
    from data_engine import storage
    from knowledge_engine.engine import get_display_knowledge_report
    from knowledge_engine.lesson import new_lesson

    broken = new_lesson("Broken Philosophy Note", "Other", status="active")
    broken.rule_type = "require_if_true"
    broken.conditions = [Condition(type="concept", name="sma")]
    storage.save_lesson(broken.to_storage_dict())
    storage.record_lesson_applications_bulk([
        (broken.id, "batch1", "BTCUSDT", "1m", "2026-01-01T00:00:00+00:00", "rejected")
        for _ in range(1000)
    ])

    good = new_lesson("Real Lesson", "Risk Management", status="active")
    good.conditions = [Condition(type="indicator_compare", indicator="rsi", op=">", value=70)]
    storage.save_lesson(good.to_storage_dict())
    storage.record_lesson_applications_bulk([
        (good.id, "batch1", "BTCUSDT", "1m", "2026-01-01T00:00:00+00:00", "approved")
        for _ in range(3)
    ])

    raw = storage.get_knowledge_report()
    assert raw["lessons_applied"] == 1003  # unfiltered, includes the broken lesson

    display = get_display_knowledge_report()
    assert display["lessons_applied"] == 3
    assert display["trades_rejected_by_lessons"] == 0
    assert display["trades_approved_by_lessons"] == 3

    # the broken lesson's history is still there in raw storage, never deleted
    assert storage.get_lesson_stats(broken.id)["trades_rejected"] == 1000


def test_compiler_auto_demotes_a_newly_saved_broken_lesson_to_draft(test_db):
    """knowledge_compiler._save_lesson_objects already demotes any
    non-enforceable lesson to draft at save time -- this only actually
    worked correctly once is_enforceable() itself was fixed. Locks in that
    a future bare/unrecognized-concept lesson can never again get saved as
    "active" and silently veto every trade."""
    from datetime import datetime, timezone

    from knowledge_compiler.compiler import _save_lesson_objects
    from knowledge_engine.lesson import new_lesson

    broken = new_lesson("Another Philosophy Note", "Other", status="active")
    broken.rule_type = "require_if_true"
    broken.conditions = [Condition(type="concept", name="rsi")]  # bare, unrecognized -- same bug shape

    now = datetime.now(timezone.utc).isoformat()
    _save_lesson_objects([{"lesson": broken, "kind": "lesson", "source_section": None}], "doc1", now)

    assert broken.status == "draft"


def test_broken_lesson_never_blocks_a_trade_via_the_real_check_call():
    """End-to-end: the exact scenario that produced 37,968,340 rejections
    with 0 approvals. After the fix, a broken lesson simply isn't
    evaluated at all (is_enforceable() False), so it can never again
    silently veto every trade."""
    import pandas as pd
    from knowledge_engine.engine import KnowledgeEngine

    df = pd.DataFrame({"open": [1, 2, 3], "high": [1, 2, 3], "low": [1, 2, 3], "close": [1, 2, 3]})
    broken = _lesson([Condition(type="concept", name="sma")], rule_type="require_if_true")
    engine = KnowledgeEngine([broken], batch_id="b1", symbol="BTCUSDT", timeframe="1m")

    assert engine.has_active_lessons() is False
    approved, reason = engine.check(df, 1, "bullish")
    assert approved is True
    assert reason is None
