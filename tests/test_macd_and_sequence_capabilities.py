"""Two new engine capabilities (Part 1 of the CRT 2.0 / Turtle Trader
rebuild task):

1. MACD wiring -- concepts.macd() already existed but was never called from
   ConfiguredStrategy.prepare_context()'s indicator loop (same bug class
   already fixed once for vwap): a macd condition silently referenced a
   column that never got created, guaranteeing 0 trades forever. Fixed by
   wiring it in plus two edge-triggered crossover helpers
   (macd_signal_crossover, macd_zero_crossover) and a "concept"-type
   dispatch (macd_signal_cross / macd_zero_cross) in configured_strategy.py.

2. Sequential/ordered-event tracking -- the engine could only check "did
   event A and event B both occur somewhere within a trailing lookback
   window" (ConfiguredStrategy._eval()'s _within()), never "did B occur
   STRICTLY AFTER A". concepts.sequential_event() is the new genuinely
   ordered primitive; concepts.sweep_invalidation_state() is the specific
   state machine CRT 2.0 needs (sweep one side -> setup active -> an
   OPPOSITE sweep before entry invalidates it).

Also covers two small additional capabilities found necessary while
building CRT 2.0/Turtle Trader with these (flagged honestly in the task
report, not silently bundled into the two gaps above): fvg_zone (FVG
re-entry containment, mirroring demand_zone/supply_zone) and
highest_high/lowest_low (rolling Donchian-style breakout levels).
"""

import pandas as pd

from backtest_engine import concepts
from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from backtest_engine.configured_strategy import ConfiguredStrategy


def _df(rows, freq="1h"):
    idx = pd.date_range("2026-01-01", periods=len(rows), freq=freq, tz="UTC")
    return pd.DataFrame({
        "open": [r[0] for r in rows], "high": [r[1] for r in rows],
        "low": [r[2] for r in rows], "close": [r[3] for r in rows],
    }, index=idx)


# --------------------------------------------------------------- MACD crossovers

def test_macd_signal_crossover_fires_bullish_at_exact_cross_bar():
    macd_line = pd.Series([-2.0, -1.0, -0.5, 0.5, 1.5, 2.0])
    signal_line = pd.Series([-1.0, -1.0, -1.0, -1.0, -1.0, -1.0])
    # diff = macd - signal: [-1, 0, 0.5, 1.5, 2.5, 3.0] -- crosses from <=0 to >0 at index 2
    bull, bear = concepts.macd_signal_crossover(macd_line, signal_line)
    assert list(bull) == [False, False, True, False, False, False]
    assert not bear.any()


def test_macd_signal_crossover_fires_bearish_at_exact_cross_bar():
    macd_line = pd.Series([2.0, 1.0, 0.5, -0.5, -1.5, -2.0])
    signal_line = pd.Series([1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
    # diff: [1, 0, -0.5, -1.5, -2.5, -3.0] -- crosses from >=0 to <0 at index 2
    bull, bear = concepts.macd_signal_crossover(macd_line, signal_line)
    assert list(bear) == [False, False, True, False, False, False]
    assert not bull.any()


def test_macd_zero_crossover_fires_bullish_and_bearish_at_exact_bars():
    macd_line = pd.Series([-3.0, -1.0, 1.0, 3.0, 1.0, -1.0, -3.0])
    bull, bear = concepts.macd_zero_crossover(macd_line)
    # crosses up at index 2 (-1 -> 1), crosses down at index 5 (1 -> -1)
    assert list(bull) == [False, False, True, False, False, False, False]
    assert list(bear) == [False, False, False, False, False, True, False]


def test_macd_actually_wired_into_configured_strategy_indicator_loop():
    """End-to-end: a real close-price series run through the ACTUAL
    prepare_context() indicator loop must produce usable macd columns and
    a firing macd_zero_cross condition -- proves the wiring, not just the
    standalone helper functions."""
    closes = [100 - i * 0.5 for i in range(40)] + [80 + i * 2.0 for i in range(30)]
    rows = [(c, c + 0.5, c - 0.5, c) for c in closes]
    df = _df(rows, freq="1h")

    cfg = StrategyConfig(
        name="macd wiring smoke test",
        timeframes={"entry": "1h"},
        indicators=[{"name": "macd", "params": {}, "role": "entry"}],
        long_entry_conditions=[Condition(type="concept", name="macd_zero_cross", direction="bullish")],
        stop_loss=SLTPSpec(type="fixed_pct", value=2.0),
        take_profit=SLTPSpec(type="fixed_pct", value=4.0),
        risk_pct=1.0,
    )
    strat = ConfiguredStrategy(cfg)

    class _FakeCtx:
        def __init__(self, frames):
            self.frames = frames

        def build(self):
            base = self.frames["entry"].add_prefix("entry_")
            return base

    ctx = _FakeCtx({"entry": df.copy()})
    merged = strat.prepare_context(ctx)
    assert any(c.startswith("entry_macd_line_") for c in merged.columns)
    assert any(c.startswith("entry_macd_bull_zero_cross_") for c in merged.columns)

    fired = [strat._eval(cfg.long_entry_conditions[0], merged, i) for i in range(len(merged))]
    assert any(fired), "macd_zero_cross bullish never fired on a sustained recovery rally"


# --------------------------------------------------------------- sequential_event

def test_sequential_event_a_then_b_in_order_fires():
    event_a = pd.Series([False, True, False, False, False])
    event_b = pd.Series([False, False, False, True, False])
    result = concepts.sequential_event(event_a, event_b)
    assert list(result) == [False, False, False, True, False]


def test_sequential_event_b_then_a_wrong_order_does_not_fire():
    event_a = pd.Series([False, False, False, True, False])
    event_b = pd.Series([False, True, False, False, False])
    # Both events occur within the same 5-bar span, but B happened BEFORE A.
    result = concepts.sequential_event(event_a, event_b)
    assert not result.any()


def test_sequential_event_a_occurs_b_never_does_not_fire():
    event_a = pd.Series([False, True, False, False, False])
    event_b = pd.Series([False, False, False, False, False])
    result = concepts.sequential_event(event_a, event_b)
    assert not result.any()


def test_sequential_event_respects_max_gap():
    event_a = pd.Series([True, False, False, False, False, False])
    event_b = pd.Series([False, False, False, False, False, True])
    assert not concepts.sequential_event(event_a, event_b, max_gap=3).any()
    assert concepts.sequential_event(event_a, event_b, max_gap=5).any()


def test_sequential_event_same_bar_does_not_count_as_after():
    event_a = pd.Series([False, True, False])
    event_b = pd.Series([False, True, False])
    result = concepts.sequential_event(event_a, event_b)
    assert not result.any()


# --------------------------------------------------------------- sweep_invalidation_state

def test_sweep_invalidation_state_bull_sweep_stays_active_until_bear_sweep():
    bull = pd.Series([False, True, False, False, False, False])
    bear = pd.Series([False, False, False, False, True, False])
    long_active, short_active = concepts.sweep_invalidation_state(bull, bear)
    assert list(long_active) == [False, True, True, True, False, False]
    assert list(short_active) == [False, False, False, False, True, True]


def test_sweep_invalidation_state_opposite_sweep_before_entry_invalidates():
    # Long setup forms at bar 1, then a bear sweep invalidates it at bar 2
    # -- BEFORE any entry could trigger. long_setup_active must be False
    # from bar 2 onward, exactly the CRT 2.0 invalidation rule.
    bull = pd.Series([False, True, False, False, False])
    bear = pd.Series([False, False, True, False, False])
    long_active, short_active = concepts.sweep_invalidation_state(bull, bear)
    assert long_active.iloc[1] == True
    assert long_active.iloc[2] == False
    assert short_active.iloc[2] == True


def test_sweep_invalidation_state_no_sweep_yet_both_inactive():
    bull = pd.Series([False, False, False])
    bear = pd.Series([False, False, False])
    long_active, short_active = concepts.sweep_invalidation_state(bull, bear)
    assert not long_active.any()
    assert not short_active.any()


# --------------------------------------------------------------- integration: sweep_invalidation_state concept

def test_sweep_invalidation_state_concept_gates_entry_correctly():
    """A long entry that also requires sweep_invalidation_state bullish
    must NOT fire once an opposite sweep has invalidated the setup, even
    though the original bull sweep is still "within window" of a plain
    lookback check -- this is exactly the scenario the old _within()-only
    mechanism could not distinguish."""
    cfg = StrategyConfig(
        name="sweep invalidation gating test",
        timeframes={"entry": "1h"},
        concepts_used=["liquidity_sweep", "sweep_invalidation_state"],
        long_entry_conditions=[Condition(type="concept", name="sweep_invalidation_state", direction="bullish")],
        stop_loss=SLTPSpec(type="fixed_pct", value=2.0),
        take_profit=SLTPSpec(type="fixed_pct", value=4.0),
        risk_pct=1.0,
    )
    strat = ConfiguredStrategy(cfg)
    raw = pd.DataFrame({
        "bull_liquidity_sweep": [False, True, False, False, False],
        "bear_liquidity_sweep": [False, False, True, False, False],
    })
    # Only "sweep_invalidation_state" in `used` here -- bull/bear_liquidity_
    # sweep are already hand-set above; passing "liquidity_sweep" too would
    # make _compute_concept_columns recompute (and overwrite) them from
    # concepts.liquidity_sweep(df), which needs real OHLC columns this
    # minimal df doesn't have.
    ConfiguredStrategy._compute_concept_columns(raw, {"sweep_invalidation_state"})
    merged = raw.add_prefix("entry_")
    cond = cfg.long_entry_conditions[0]
    results = [strat._eval(cond, merged, i) for i in range(len(merged))]
    assert results == [False, True, False, False, False]


# --------------------------------------------------------------- fvg_zone containment

def test_fvg_zone_containment_true_only_when_price_back_inside():
    cfg = StrategyConfig(name="fvg zone test", timeframes={"entry": "1h"})
    strat = ConfiguredStrategy(cfg)
    df = pd.DataFrame({
        "close": [100.0, 105.0, 97.0, 100.5],
        "entry_fvg_bull_low": [None, 99.0, 99.0, 99.0],
        "entry_fvg_bull_high": [None, 101.0, 101.0, 101.0],
        "entry_fvg_bear_low": [None, None, None, None],
        "entry_fvg_bear_high": [None, None, None, None],
    })
    cond = Condition(type="concept", name="fvg_zone", direction="bullish")
    results = [strat._eval(cond, df, i) for i in range(len(df))]
    assert results == [False, False, False, True]


# --------------------------------------------------------------- highest_high / lowest_low

def test_rolling_high_low_are_causal_and_exclude_current_bar():
    high = pd.Series([10, 12, 9, 15, 8])
    low = pd.Series([5, 4, 3, 6, 2])
    rh = concepts.rolling_high(high, 3)
    rl = concepts.rolling_low(low, 3)
    # rh[3] = max(high[0:3]) = max(10,12,9) = 12 (bar 3's own high=15 excluded)
    assert rh.iloc[3] == 12
    # rl[3] = min(low[0:3]) = min(5,4,3) = 3
    assert rl.iloc[3] == 3


def test_highest_high_indicator_wired_and_breakout_condition_fires():
    closes = [100, 101, 99, 100, 98, 97, 99, 101, 130]
    rows = [(c, c + 1, c - 1, c) for c in closes]
    df = _df(rows)
    cfg = StrategyConfig(
        name="donchian breakout smoke test",
        timeframes={"entry": "1h"},
        indicators=[{"name": "highest_high", "params": {"period": 5}, "role": "entry"}],
        entry_conditions=[Condition(type="price_compare", indicator="highest_high", params={"period": 5}, op=">")],
        stop_loss=SLTPSpec(type="fixed_pct", value=2.0),
        take_profit=SLTPSpec(type="fixed_pct", value=4.0),
        risk_pct=1.0,
    )
    strat = ConfiguredStrategy(cfg)

    class _FakeCtx:
        def __init__(self, frames):
            self.frames = frames

        def build(self):
            return self.frames["entry"].add_prefix("entry_")

    merged = strat.prepare_context(_FakeCtx({"entry": df.copy()}))
    merged = strat.prepare(merged)  # aliases entry_close -> close, etc., like the real engine does
    results = [strat._eval(cfg.entry_conditions[0], merged, i) for i in range(len(merged))]
    assert results[-1] == True  # the final bar (130) breaks the preceding 5-bar high
    assert not any(results[:5])  # not enough prior bars yet
