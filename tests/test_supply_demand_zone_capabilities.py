"""Three new engine capabilities built for a Supply/Demand Zone strategy
(direct manual construction, no strategy_parser.py, no ai_integration/):

1. concepts.consolidation_impulse_zones() -- a multi-bar tight-range
   consolidation immediately followed by a sharp directional break, marked
   as a demand/supply zone. Genuinely different from order_blocks() /
   mitigation_blocks() (both single-origin-candle), confirmed missing by
   the capability check that preceded this task.
2. The "demand_zone"/"supply_zone" concept condition in
   configured_strategy.py -- a real, fresh-every-bar "is price currently
   back inside this zone" containment check, as opposed to the
   permanently-true-once-triggered existence check every other zone
   concept uses.
3. concepts.valid_structure_trend() -- sequential, stateful "valid low/high"
   trend tracking (a low only counts once price breaks the prior high;
   trend only flips when that specific valid low is later broken, not on
   every minor lower low).

Also covers the follow-up fix: risk_reward_filter_uses_take_profit, which
makes the min_risk_reward_filter pre-trade gate check against the SAME
level the trade will actually exit at, instead of a separate
primary_target_lookback_bars reference that could silently disagree with
the real take-profit.
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


# --------------------------------------------------------------- capability 1

def test_demand_zone_detected_from_consolidation_then_up_impulse():
    rows = [
        (100, 101, 99, 100.5), (100.5, 101.5, 99.5, 100.8), (100.8, 101.8, 99.8, 101.0),
        (101.0, 102.0, 100.0, 101.3), (101.3, 102.3, 100.3, 101.5),
        # 3-bar tight consolidation: window low=101.0, window high=102.1
        (101.5, 102.0, 101.0, 101.6), (101.6, 102.1, 101.1, 101.7), (101.7, 102.0, 101.2, 101.6),
        # sharp up impulse clearing the consolidation high
        (101.6, 112.0, 101.5, 112.0), (112.0, 113.0, 111.0, 112.5),
    ]
    df = _df(rows)
    demand_low, demand_high, supply_low, supply_high = concepts.consolidation_impulse_zones(
        df, consolidation_bars=3, tightness_mult=1.5, impulse_atr_mult=1.5, atr_period=5)

    assert pd.isna(demand_low.iloc[7])  # not yet formed before the impulse bar
    assert demand_low.iloc[8] == 101.0
    assert demand_high.iloc[8] == 102.1
    assert demand_low.iloc[9] == 101.0  # forward-filled after formation
    assert demand_high.iloc[9] == 102.1
    assert pd.isna(supply_low.iloc[9])  # no supply zone in this data


def test_supply_zone_detected_from_consolidation_then_down_impulse():
    rows = [
        (100, 101, 99, 100.5), (100.5, 101.5, 99.5, 100.8), (100.8, 101.8, 99.8, 101.0),
        (101.0, 102.0, 100.0, 101.3), (101.3, 102.3, 100.3, 101.5),
        (101.5, 102.0, 101.0, 101.6), (101.6, 102.1, 101.1, 101.7), (101.7, 102.0, 101.2, 101.6),
        # sharp down impulse clearing the consolidation low
        (101.6, 101.7, 91.0, 91.0), (91.0, 92.0, 90.0, 91.5),
    ]
    df = _df(rows)
    demand_low, demand_high, supply_low, supply_high = concepts.consolidation_impulse_zones(
        df, consolidation_bars=3, tightness_mult=1.5, impulse_atr_mult=1.5, atr_period=5)

    assert supply_low.iloc[8] == 101.0
    assert supply_high.iloc[8] == 102.1
    assert supply_low.iloc[9] == 101.0
    assert pd.isna(demand_low.iloc[9])


def test_no_zone_when_range_is_not_actually_tight():
    """A steadily trending staircase (each bar's range not overlapping the
    others much) must NOT be mistaken for a consolidation, even if a sharp
    bar follows it -- proves the tightness measure is real, not just "any
    3 bars before a big bar"."""
    rows = [
        (100, 101, 99, 100.5), (100.5, 101.5, 99.5, 100.8), (100.8, 101.8, 99.8, 101.0),
        (101.0, 102.0, 100.0, 101.3), (101.3, 102.3, 100.3, 101.5),
        # trending staircase, NOT tight (each bar's range is ~2, same as the
        # baseline -- the 3-bar window span is much wider than one bar's range)
        (101.5, 103.5, 101.5, 103.0), (103.0, 105.5, 103.0, 105.0), (105.0, 108.0, 105.0, 107.5),
        (107.5, 118.0, 107.4, 118.0), (118.0, 119.0, 117.0, 118.5),
    ]
    df = _df(rows)
    demand_low, demand_high, supply_low, supply_high = concepts.consolidation_impulse_zones(
        df, consolidation_bars=3, tightness_mult=1.5, impulse_atr_mult=1.5, atr_period=5)
    assert pd.isna(demand_low.iloc[9])


# --------------------------------------------------------------- capability 2

def _zone_cfg():
    return StrategyConfig(name="Zone Reentry Test", timeframes={"entry": "1h"},
                           concepts_used=["demand_zone"])


def test_demand_zone_reentry_is_false_at_formation_and_true_only_on_actual_return():
    cfg = _zone_cfg()
    strat = ConfiguredStrategy(cfg)
    rows = [(100, 101, 99, 100)] * 6
    df = _df(rows)
    df["entry_demand_low"] = 100.0
    df["entry_demand_high"] = 105.0
    # bar0-1: price far above the zone (just formed via an impulse, so it's
    #         naturally outside) -- bar2-3: price returns inside [100,105]
    #         -- bar4: leaves again -- bar5: still outside
    df["close"] = [110.0, 108.0, 104.0, 102.0, 106.0, 109.0]
    prepared = strat.prepare(df)
    cond = Condition(type="concept", name="demand_zone", role="entry")
    results = [strat._eval(cond, prepared, i) for i in range(6)]
    assert results == [False, False, True, True, False, False]


def test_supply_zone_reentry_symmetric():
    cfg = StrategyConfig(name="Supply Reentry Test", timeframes={"entry": "1h"},
                          concepts_used=["supply_zone"])
    strat = ConfiguredStrategy(cfg)
    rows = [(100, 101, 99, 100)] * 5
    df = _df(rows)
    df["entry_supply_low"] = 100.0
    df["entry_supply_high"] = 105.0
    df["close"] = [90.0, 101.0, 96.0, 102.0, 91.0]
    prepared = strat.prepare(df)
    cond = Condition(type="concept", name="supply_zone", role="entry")
    results = [strat._eval(cond, prepared, i) for i in range(5)]
    assert results == [False, True, False, True, False]


def test_demand_zone_condition_false_when_no_zone_exists_yet():
    cfg = _zone_cfg()
    strat = ConfiguredStrategy(cfg)
    rows = [(100, 101, 99, 100)] * 3
    df = _df(rows)
    df["entry_demand_low"] = float("nan")
    df["entry_demand_high"] = float("nan")
    prepared = strat.prepare(df)
    cond = Condition(type="concept", name="demand_zone", role="entry")
    assert strat._eval(cond, prepared, 0) is False


# --------------------------------------------------------------- capability 3

def _leg(start, end, bars):
    step = (end - start) / bars
    out = []
    for i in range(bars):
        lo = start + step * i
        c = lo + step
        h = max(lo, c) + 0.3
        l = min(lo, c) - 0.3
        out.append((lo, h, l, c))
    return out


def _valid_trend_df():
    rows = []
    rows += _leg(100, 120, 6)   # initial rally -> first swing high ~120.3
    rows += _leg(120, 110, 5)   # pullback -> swing low ~109.7
    rows += _leg(110, 130, 5)   # breaks prior high (120.3) -> validates the 109.7 low; new swing high ~130.3
    rows += _leg(130, 115, 5)   # pulls back to ~114.7 -- a "lower low" in raw swing terms, but still ABOVE
                                 # the valid low (109.7) and never rallies back past 130.3, so it never
                                 # gets validated either -- must NOT flip the trend
    rows += _leg(115, 125, 4)   # minor bounce, doesn't reclaim 130.3
    rows += _leg(125, 105, 5)   # genuine break below the valid low (109.7) -> trend must flip here
    rows += _leg(105, 95, 4)    # downtrend continues
    return _df(rows)


def test_uptrend_established_after_breaking_prior_high():
    df = _valid_trend_df()
    trend = concepts.valid_structure_trend(df, lookback=2)
    assert trend.iloc[13] == "up"


def test_minor_lower_low_that_never_broke_a_prior_high_does_not_flip_trend():
    df = _valid_trend_df()
    trend = concepts.valid_structure_trend(df, lookback=2)
    # bars 14-27 span the pullback to ~114.7 and the failed bounce to ~125 --
    # none of it ever closes below the valid low (109.7), so trend must stay up
    for i in range(14, 28):
        assert trend.iloc[i] == "up", f"bar {i} flipped trend on an unvalidated lower low"


def test_trend_flips_only_once_the_actual_valid_low_is_broken():
    df = _valid_trend_df()
    trend = concepts.valid_structure_trend(df, lookback=2)
    assert trend.iloc[28] == "down"
    assert trend.iloc[33] == "down"


def test_no_trend_before_any_valid_low_or_high_has_formed():
    df = _valid_trend_df()
    trend = concepts.valid_structure_trend(df, lookback=2)
    assert trend.iloc[0] is None


def test_structure_stop_loss_prefers_demand_zone_over_generic_fallbacks():
    cfg = StrategyConfig(name="SL Wiring Test", timeframes={"entry": "1h"},
                          concepts_used=["demand_zone", "resistance"],
                          stop_loss=SLTPSpec(type="structure"))
    strat = ConfiguredStrategy(cfg)
    rows = [(100, 101, 99, 100)] * 2
    df = _df(rows)
    df["entry_demand_low"] = 95.0
    df["entry_support"] = 90.0  # a generic fallback that must lose to the zone-specific one
    prepared = strat.prepare(df)
    sl = strat._compute_stop_loss(prepared, 0, price=100.0, direction="bullish")
    assert sl == 95.0


def test_structure_stop_loss_falls_back_when_no_demand_zone_present():
    cfg = StrategyConfig(name="SL Fallback Test", timeframes={"entry": "1h"},
                          concepts_used=["resistance"],
                          stop_loss=SLTPSpec(type="structure"))
    strat = ConfiguredStrategy(cfg)
    rows = [(100, 101, 99, 100)] * 2
    df = _df(rows)
    df["entry_support"] = 90.0
    prepared = strat.prepare(df)
    sl = strat._compute_stop_loss(prepared, 0, price=100.0, direction="bullish")
    assert sl == 90.0


def _fixed_pct_cfg(sl_pct, tp_pct, min_rr, use_tp_for_filter=True, lookback_bars=None):
    return StrategyConfig(
        name="RR Filter Fix Test", timeframes={"entry": "1h"},
        long_entry_conditions=[Condition(type="candle_range_pct", params={"min_pct": 0.0, "max_pct": 1000.0}, role="entry")],
        stop_loss=SLTPSpec(type="fixed_pct", value=sl_pct),
        take_profit=SLTPSpec(type="fixed_pct", value=tp_pct),
        min_risk_reward_filter=min_rr,
        risk_reward_filter_uses_take_profit=use_tp_for_filter,
        primary_target_lookback_bars=lookback_bars,
    )


def test_rr_filter_against_take_profit_passes_when_real_rr_clears_threshold():
    # SL=2%, TP=6% -> real R:R = 3.0, filter requires 2.5 -> should pass
    cfg = _fixed_pct_cfg(sl_pct=2.0, tp_pct=6.0, min_rr=2.5)
    strat = ConfiguredStrategy(cfg)
    df = _df([(100, 101, 99, 100)] * 3)
    signal = strat.on_bar(strat.prepare(df), 2, None)
    assert signal is not None and signal.action == "buy"
    assert signal.take_profit == 106.0
    assert signal.stop_loss == 98.0
    real_rr = abs(signal.take_profit - 100.0) / abs(100.0 - signal.stop_loss)
    assert real_rr == 3.0


def test_rr_filter_against_take_profit_rejects_when_real_rr_is_actually_below_threshold():
    # SL=2%, TP=4% -> real R:R = 2.0, filter requires 2.5 -> must be rejected
    # -- this is exactly the bug that was found: a separate lookback-based
    # reference could have let this through even though the REAL exit R:R
    # is only 2.0.
    cfg = _fixed_pct_cfg(sl_pct=2.0, tp_pct=4.0, min_rr=2.5)
    strat = ConfiguredStrategy(cfg)
    df = _df([(100, 101, 99, 100)] * 3)
    signal = strat.on_bar(strat.prepare(df), 2, None)
    assert signal is None


def test_old_lookback_based_filter_reference_still_works_when_flag_is_off():
    """Backward compatibility: a strategy that explicitly wants the OLDER,
    separate primary_target_lookback_bars reference (not the actual take-
    profit) must be unaffected by this fix."""
    cfg = _fixed_pct_cfg(sl_pct=2.0, tp_pct=4.0, min_rr=2.5, use_tp_for_filter=False, lookback_bars=5)
    strat = ConfiguredStrategy(cfg)
    rows = [(100, 130, 70, 100)] * 6  # wide preceding bars -> a far primary_target -> should pass despite the near 2:1 take_profit
    df = _df(rows)
    signal = strat.on_bar(strat.prepare(df), 5, None)
    assert signal is not None  # passes using the lookback reference, not the real 2:1 take_profit


def test_valid_structure_trend_condition_wires_into_configured_strategy():
    """The "concept" condition wrapper (name="valid_structure_trend") reads
    the same computed column the way every other role-aware concept does."""
    cfg = StrategyConfig(name="Trend Wiring Test", timeframes={"entry": "1h"},
                          concepts_used=["valid_structure_trend"])
    strat = ConfiguredStrategy(cfg)
    rows = [(100, 101, 99, 100)] * 3
    df = _df(rows)
    df["entry_structure_trend"] = pd.array(["up", "down", None], dtype=object)
    prepared = strat.prepare(df)
    bullish = Condition(type="concept", name="valid_structure_trend", direction="bullish", role="entry")
    bearish = Condition(type="concept", name="valid_structure_trend", direction="bearish", role="entry")
    assert strat._eval(bullish, prepared, 0) is True
    assert strat._eval(bullish, prepared, 1) is False
    assert strat._eval(bearish, prepared, 1) is True
    assert strat._eval(bearish, prepared, 2) is False
