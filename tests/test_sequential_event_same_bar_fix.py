"""Real bug found while building Asian Range London Sweep: sequential_event()
updated last_a_idx to the CURRENT bar before checking event_b at that same
bar, so when event_a and event_b are BOTH true on one bar (not mutually
exclusive here -- a single candle can both sweep below a level AND close
back above it), that bar's own event_a silently clobbered a genuinely
earlier, still-valid event_a reference, causing a real prior sweep to fail
to pair with a later reclaim. Confirmed on real AAVEUSDT data: a sweep at
bar 200 failed to pair with a reclaim at bar 229 purely because bar 229
ALSO satisfied event_a."""

import pandas as pd

from backtest_engine import concepts


def test_earlier_event_a_survives_a_later_bar_where_a_and_b_are_both_true():
    #                idx:   0     1      2      3     4
    event_a = pd.Series([True, False, False, False, True])   # bar 0 AND bar 4 both fire a
    event_b = pd.Series([False, False, False, False, True])  # bar 4 also fires b
    # bar 4's own event_a must NOT prevent bar 0's earlier event_a from
    # pairing with bar 4's event_b.
    result = concepts.sequential_event(event_a, event_b)
    assert result.iloc[4] == True


def test_no_earlier_event_a_same_bar_a_and_b_does_not_fire():
    event_a = pd.Series([False, True])
    event_b = pd.Series([False, True])
    result = concepts.sequential_event(event_a, event_b)
    assert not result.any()


def test_reproduces_the_real_asian_range_bug_scenario():
    # bar 0: event_a only (the legitimate earlier sweep)
    # bars 1-2: neither
    # bar 3: event_a AND event_b both true (a candle that both sweeps and
    # reclaims) -- must still correctly pair with bar 0's earlier sweep.
    event_a = pd.Series([True, False, False, True])
    event_b = pd.Series([False, False, False, True])
    result = concepts.sequential_event(event_a, event_b)
    assert result.iloc[3] == True
