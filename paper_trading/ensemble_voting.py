"""Ensemble Voting Confirmation (Grand Feature Expansion, Phase 5 Feature
10): requires agreement from a minimum number of INDEPENDENT strategies
(or the shared lessons book) on the same symbol+direction within the same
tick, before any of their candidates can open. Confirmed absent before
this was built -- every strategy runs fully independently; confluence.py
scores ONE candidate's own signal quality, never a vote across multiple
strategies' candidates.

Off by default, and always risk-REDUCING when turned on -- requiring
agreement can only make trading MORE conservative (fewer entries), never
less, same category as the existing Multi-Timeframe confirmation
requirement (backtest_engine/mtf_context.py)."""

from paper_trading import guards


def agreeing_book_count(approved_candidates, direction):
    """Distinct books (strategy_id, or the shared '__lessons__' book) among
    this tick's already-approved candidates for ONE symbol that agree on
    `direction` ('bullish'/'bearish')."""
    return len({guards.book_key(c) for c in approved_candidates if c["direction"] == direction})


def has_enough_agreement(approved_candidates, direction, min_agreeing):
    return agreeing_book_count(approved_candidates, direction) >= min_agreeing
