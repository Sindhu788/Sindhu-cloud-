"""Batch 7, Task 4: Signal Quality Grade -- deterministic function of the
existing confluence_result/reliability_result dicts only (same shapes as
paper_trading.confluence.score_confluence()/pattern_stats.classify()
already return). No new scoring inputs, no AI. These tests lock in the
exact boundary behavior of paper_trading.signal_explainer.grade_signal().
"""

from paper_trading import signal_explainer


def _confluence(passed, total):
    return {"label": f"test -- {passed}/{total}", "passed": passed, "total": total, "factors": []}


def _reliability(status):
    return {"status": status, "reliable": status != "insufficient_data",
            "sample_size": 40, "win_rate_pct": 60.0, "min_sample_size": 25,
            "ci_lower_pct": 45.0, "ci_upper_pct": 75.0}


def test_a_plus_requires_both_reliable_good_and_strong_confluence():
    result = signal_explainer.grade_signal(_confluence(3, 4), _reliability("reliable_good"))  # 0.75 ratio
    assert result["grade"] == "A+"


def test_strong_confluence_exactly_at_threshold_still_counts():
    result = signal_explainer.grade_signal(_confluence(3, 4), _reliability("reliable_good"))  # exactly 0.75
    assert result["grade"] == "A+"


def test_just_below_strong_threshold_with_reliable_good_is_a_not_a_plus():
    result = signal_explainer.grade_signal(_confluence(2, 3), _reliability("reliable_good"))  # 0.666...
    assert result["grade"] == "A"


def test_reliable_good_alone_without_confluence_data_is_a():
    result = signal_explainer.grade_signal(None, _reliability("reliable_good"))
    assert result["grade"] == "A"


def test_strong_confluence_alone_without_reliability_is_a():
    result = signal_explainer.grade_signal(_confluence(4, 4), _reliability("insufficient_data"))
    assert result["grade"] == "A"


def test_moderate_confluence_alone_is_b():
    result = signal_explainer.grade_signal(_confluence(2, 4), _reliability("insufficient_data"))  # exactly 0.5
    assert result["grade"] == "B"


def test_just_below_moderate_threshold_is_c():
    result = signal_explainer.grade_signal(_confluence(1, 3), _reliability("insufficient_data"))  # 0.333
    assert result["grade"] == "C"


def test_no_data_at_all_is_c():
    result = signal_explainer.grade_signal(None, None)
    assert result["grade"] == "C"


def test_reliable_bad_always_caps_at_c_even_with_perfect_confluence():
    """A statistically PROVEN losing pattern (Wilson gate) must never be
    graded better than C, no matter how strong confluence looks this one
    time -- safety overrides the qualitative signal."""
    result = signal_explainer.grade_signal(_confluence(4, 4), _reliability("reliable_bad"))
    assert result["grade"] == "C"


def test_every_grade_result_includes_a_plain_language_reason():
    for conf, rel in [
        (_confluence(4, 4), _reliability("reliable_good")),
        (_confluence(2, 3), _reliability("reliable_good")),
        (_confluence(2, 4), _reliability("insufficient_data")),
        (None, None),
    ]:
        result = signal_explainer.grade_signal(conf, rel)
        assert result["reason"]
