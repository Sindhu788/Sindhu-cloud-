"""Tests for paper_trading.pattern_stats -- the Wilson-score statistical
reliability gate shared by Pattern Auto-Avoid and Lesson Auto-Apply."""

from paper_trading import pattern_stats


def test_below_min_sample_is_always_insufficient_even_at_extreme_win_rate():
    # 4/5 = 80% win rate -- looks extreme, but n=5 is nowhere near reliable.
    result = pattern_stats.classify(wins=4, n=5)
    assert result["status"] == "insufficient_data"
    assert result["reliable"] is False
    assert result["ci_lower_pct"] is None
    assert "insufficient data" in result["conclusion"]


def test_exactly_at_threshold_is_evaluated():
    n = pattern_stats.MIN_SAMPLE_SIZE
    result = pattern_stats.classify(wins=n, n=n)  # 100% win rate over the full threshold
    assert result["reliable"] is True
    assert result["status"] == "reliable_good"


def test_one_below_threshold_is_insufficient():
    n = pattern_stats.MIN_SAMPLE_SIZE - 1
    result = pattern_stats.classify(wins=n, n=n)
    assert result["status"] == "insufficient_data"


def test_confidently_bad_pattern():
    # 5/25 = 20% win rate over 25 trades -- should be a confident loser.
    result = pattern_stats.classify(wins=5, n=25)
    assert result["reliable"] is True
    assert result["status"] == "reliable_bad"
    assert result["ci_upper_pct"] <= pattern_stats.BAD_UPPER_BOUND * 100


def test_confidently_good_pattern():
    # 20/25 = 80% win rate over 25 trades -- should be a confident winner.
    result = pattern_stats.classify(wins=20, n=25)
    assert result["reliable"] is True
    assert result["status"] == "reliable_good"
    assert result["ci_lower_pct"] >= pattern_stats.GOOD_LOWER_BOUND * 100


def test_reliable_but_inconclusive_near_50_percent():
    # 13/25 = 52% win rate -- enough samples, but nowhere near confidently
    # one-sided given how wide the interval still is at this sample size.
    result = pattern_stats.classify(wins=13, n=25)
    assert result["reliable"] is True
    assert result["status"] == "reliable_inconclusive"


def test_zero_trades_degrades_gracefully():
    result = pattern_stats.classify(wins=0, n=0)
    assert result["status"] == "insufficient_data"
    assert result["win_rate_pct"] == 0.0


def test_wilson_interval_bounds_stay_within_zero_one():
    lower, upper = pattern_stats.wilson_interval(wins=0, n=25)
    assert 0.0 <= lower <= upper <= 1.0
    lower, upper = pattern_stats.wilson_interval(wins=25, n=25)
    assert 0.0 <= lower <= upper <= 1.0


def test_wilson_interval_narrows_with_more_samples_at_same_win_rate():
    # Same 60% win rate, but a much bigger sample should produce a tighter
    # (narrower) confidence interval -- the core promise of the method.
    small_lower, small_upper = pattern_stats.wilson_interval(wins=15, n=25)
    large_lower, large_upper = pattern_stats.wilson_interval(wins=150, n=250)
    assert (large_upper - large_lower) < (small_upper - small_lower)
