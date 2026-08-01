"""Task 3 (Priority Batch 1) -- concepts.candle_break must be edge-triggered
(fires on only the first bar that breaks a reference candle's extreme), not
level-triggered (previously stayed True on every subsequent bar that also
happened to still be beyond that extreme). Diagnosed against the PDH-PDL
Signal Candle Strategy's 119,255-trade / 1.62%-win real backtest.
"""

import pandas as pd

from backtest_engine import concepts


def _df(rows):
    """rows: list of (open, high, low, close)."""
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"])


def test_bear_break_fires_once_per_reference_candle_not_every_bar_below_it():
    # bar0: bearish reference candle, low=95
    # bar1: breaks below 95 (low=90) -- should fire (first break)
    # bar2: still below 95 (low=88, and still no new bearish candle) -- must NOT fire again
    # bar3: still below 95 (low=85) -- must NOT fire again
    rows = [
        (100, 101, 95, 96),   # bar0: bearish (close<open), reference low=95
        (96, 97, 90, 96.5),   # bar1: bullish candle, low=90 < 95 -> first break
        (96.5, 97, 88, 96.6),  # bar2: bullish candle, low=88 < 95 -> still same reference, must not re-fire
        (96.6, 97, 85, 96.7),  # bar3: bullish candle, low=85 < 95 -> still same reference, must not re-fire
    ]
    df = _df(rows)
    _, bear_break = concepts.candle_break(df)
    assert list(bear_break) == [False, True, False, False]


def test_bear_break_can_fire_again_after_a_fresh_reference_candle():
    rows = [
        (100, 101, 95, 96),    # bar0: bearish, reference low=95
        (96, 97, 90, 96.5),    # bar1: low=90 < 95 -> break #1
        (96.5, 97, 85, 96.0),  # bar2: bearish (close<open), NEW reference low=85
        (96.0, 97, 80, 96.1),  # bar3: low=80 < 85 -> break #2 (fresh reference, allowed)
    ]
    df = _df(rows)
    _, bear_break = concepts.candle_break(df)
    assert list(bear_break) == [False, True, False, True]


def test_bull_break_mirrors_bear_break():
    rows = [
        (100, 105, 99, 99.5),   # bar0: bearish -- not a bullish reference
        (99.5, 105, 99, 106),   # bar1: bullish (close>open), reference high=105... wait, own high 105 not yet a "prior" ref
        (106, 110, 105, 107),   # bar2: bullish, high=110 > prior bullish ref (105 from bar1) -> break #1
        (107, 112, 106, 108),   # bar3: bullish, high=112 > 110? reference still bar1's 105 (no new bearish reset needed for bull group) -- but group only advances on a NEW bullish candle, and bar2 itself is bullish so it becomes the new reference
    ]
    df = _df(rows)
    bull_break, _ = concepts.candle_break(df)
    # bar1 is the first bullish candle -> no prior reference yet, can't break
    assert bull_break[0] == False
    assert bull_break[1] == False
    # bar2 breaks bar1's high (105) -- but bar2 is itself bullish, becoming the new reference for bar3
    assert bull_break[2] == True
    # bar3 must be judged against bar2's high (110), not bar1's -- and 112 > 110, so it's a genuine new break
    assert bull_break[3] == True


def test_edge_trigger_never_reads_the_current_bars_own_extreme():
    """A candle can never trigger a break of itself -- causal by
    construction (unchanged by this fix, still verified here)."""
    rows = [(100, 101, 95, 96)]
    df = _df(rows)
    bull_break, bear_break = concepts.candle_break(df)
    assert bull_break[0] == False
    assert bear_break[0] == False
