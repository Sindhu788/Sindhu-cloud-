"""Double Confirmation CHoCH with Liquidity Trap needs a strict 3-stage
event order: initial CHoCH ("wake-up call") -> retest/sweep strictly AFTER
it -> a SECOND CHoCH strictly after that retest. Built as two chained
concepts.sequential_event() calls (see configured_strategy.py's
_compute_concept_columns, "double_choch_confirmation" block) instead of a
bespoke state machine -- this file proves the composition actually enforces
strict ordering end-to-end, including the exact "right events, wrong order"
case the old window-based _within() approximation could not reject.
"""

import pandas as pd

from backtest_engine import concepts
from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from backtest_engine.configured_strategy import ConfiguredStrategy


def _confirmation(choch, sweep):
    stage2 = concepts.sequential_event(choch, sweep)
    return concepts.sequential_event(stage2, choch)


def test_correct_order_choch_then_sweep_then_second_choch_confirms():
    #                idx:  0      1      2      3      4      5
    choch = pd.Series([False, True, False, False, False, True])
    sweep = pd.Series([False, False, False, True, False, False])
    confirmed = _confirmation(choch, sweep)
    assert list(confirmed) == [False, False, False, False, False, True]


def test_sweep_before_initial_choch_never_confirms():
    # Sweep happens BEFORE any CHoCH at all -- can't be a "retest of" an
    # initial CHoCH that hasn't happened yet.
    choch = pd.Series([False, False, True, False, False, True])
    sweep = pd.Series([True, False, False, False, False, False])
    confirmed = _confirmation(choch, sweep)
    assert not confirmed.any()


def test_second_choch_before_sweep_never_confirms_even_in_same_window():
    # Right events (an initial CHoCH, a sweep, and a later CHoCH) all occur
    # within a tight span, but the SECOND CHoCH fires BEFORE the sweep --
    # wrong order. The old window-based co-occurrence check would have
    # wrongly accepted this (all three events present within N bars); the
    # sequential composition must correctly reject it.
    choch = pd.Series([True, False, True, False, False, False])
    sweep = pd.Series([False, False, False, False, True, False])
    confirmed = _confirmation(choch, sweep)
    assert not confirmed.any()


def test_only_initial_choch_no_retest_no_second_choch_never_confirms():
    choch = pd.Series([False, True, False, False, False])
    sweep = pd.Series([False, False, False, False, False])
    confirmed = _confirmation(choch, sweep)
    assert not confirmed.any()


def test_initial_choch_and_retest_but_no_second_choch_never_confirms():
    choch = pd.Series([False, True, False, False, False])
    sweep = pd.Series([False, False, True, False, False])
    confirmed = _confirmation(choch, sweep)
    assert not confirmed.any()


def test_double_choch_confirmation_concept_wired_end_to_end():
    """Real ConfiguredStrategy path: the "double_choch_confirmation" concept
    condition must read the columns _compute_concept_columns() builds and
    fire on exactly the confirmation bar."""
    cfg = StrategyConfig(
        name="double choch wiring test",
        timeframes={"entry": "1h"},
        concepts_used=["choch", "liquidity_sweep", "double_choch_confirmation"],
        long_entry_conditions=[Condition(type="concept", name="double_choch_confirmation", direction="bullish", lookback_bars=1)],
        stop_loss=SLTPSpec(type="fixed_pct", value=2.0),
        take_profit=SLTPSpec(type="fixed_pct", value=4.0),
        risk_pct=1.0,
    )
    strat = ConfiguredStrategy(cfg)
    n = 6
    raw = pd.DataFrame({
        "bull_choch": [False, True, False, False, False, True],
        "bear_choch": [False] * n,
        "bull_liquidity_sweep": [False, False, False, True, False, False],
        "bear_liquidity_sweep": [False] * n,
    })
    # Only "double_choch_confirmation" in `used` -- bull_choch/bear_choch/
    # bull_liquidity_sweep/bear_liquidity_sweep are already hand-set above;
    # including "choch"/"liquidity_sweep" too would make
    # _compute_concept_columns recompute (and overwrite) them from real
    # OHLC columns this minimal df doesn't have.
    ConfiguredStrategy._compute_concept_columns(raw, {"double_choch_confirmation"})
    merged = raw.add_prefix("entry_")
    cond = cfg.long_entry_conditions[0]
    results = [strat._eval(cond, merged, i) for i in range(n)]
    assert results == [False, False, False, False, False, True]
