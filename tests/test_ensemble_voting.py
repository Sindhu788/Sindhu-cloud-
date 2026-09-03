"""Grand Feature Expansion, Phase 5 Feature 10: Ensemble Voting
Confirmation (paper_trading/ensemble_voting.py) -- requires agreement from
a minimum number of INDEPENDENT strategies on the same symbol+direction
within the same tick before any of them can open. Confirmed absent before
this was built: every strategy ran fully independently. Always
risk-REDUCING when enabled -- can only make trading more conservative.
"""

from paper_trading import ensemble_voting


def _candidate(strategy_id, direction):
    return {"strategy_id": strategy_id, "direction": direction}


def test_no_candidates_means_zero_agreement():
    assert ensemble_voting.agreeing_book_count([], "bullish") == 0


def test_counts_only_distinct_books_agreeing_on_the_direction():
    candidates = [
        _candidate("stratA", "bullish"),
        _candidate("stratB", "bullish"),
        _candidate("stratC", "bearish"),
    ]
    assert ensemble_voting.agreeing_book_count(candidates, "bullish") == 2
    assert ensemble_voting.agreeing_book_count(candidates, "bearish") == 1


def test_lesson_only_candidates_share_one_book():
    candidates = [
        _candidate(None, "bullish"),  # lesson-only -- shares "__lessons__"
        _candidate(None, "bullish"),  # another lesson -- SAME shared book, not a second vote
        _candidate("stratA", "bullish"),
    ]
    # Only 2 distinct books agree (the shared lessons book + stratA), even
    # though 3 individual candidates exist.
    assert ensemble_voting.agreeing_book_count(candidates, "bullish") == 2


def test_has_enough_agreement_true_and_false():
    candidates = [_candidate("stratA", "bullish"), _candidate("stratB", "bullish")]
    assert ensemble_voting.has_enough_agreement(candidates, "bullish", 2) is True
    assert ensemble_voting.has_enough_agreement(candidates, "bullish", 3) is False


def test_a_single_strategys_own_signal_never_counts_as_two():
    candidates = [_candidate("stratA", "bullish")]
    assert ensemble_voting.has_enough_agreement(candidates, "bullish", 2) is False
