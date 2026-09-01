"""Two new gaps confirmed by the CRT 2.0 / Turtle Trader rebuild batch:

1. Stop-loss buffer floor -- CRT 2.0's 0.15% signal_candle buffer was
   smaller than this platform's real round-trip transaction cost (commission
   + slippage), so stops got hit by fee/slippage noise alone regardless of
   trade direction. Confirmed against the REAL platform default (sindhu_web/
   api/backtesting.py's RunRequest: commission_pct=0.1, slippage_pct=0.05,
   spread_pct unset/0) -- not the lower ad-hoc values used in this session's
   own scratch batch scripts. Round trip = 2 * (commission_pct + slippage_pct)
   = 2 * (0.1 + 0.05) = 0.30%. This isn't a code bug (no hardcoded 0.15%
   default exists anywhere in backtest_engine -- confirmed by a direct grep),
   it's a per-strategy parameter choice; the fix is a documented, computed
   minimum (>= 3x round-trip = 0.90%, using 1.0% going forward) applied to
   every buffer-based stop-loss built in this task, not a new code path.

2. exit_conditions had no direction-awareness: the SAME exit rule bucket
   applied identically to long and short positions, with no way to express
   "a bearish break exits longs, a bullish break exits shorts" as two
   separate rules. Fixed via Condition.exit_direction (None = both sides,
   unchanged default; "bullish"/"bearish" = only checked while the open
   position is that side).
"""

import pandas as pd

from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from backtest_engine.configured_strategy import ConfiguredStrategy


def _cfg_with_direction_aware_exits():
    return StrategyConfig(
        name="direction aware exit test",
        timeframes={"entry": "1h"},
        concepts_used=["candle_break"],
        entry_conditions=[Condition(type="concept", name="candle_break", direction="bullish")],
        exit_conditions=[
            Condition(type="concept", name="candle_break", direction="bearish", exit_direction="bullish"),
            Condition(type="concept", name="candle_break", direction="bullish", exit_direction="bearish"),
        ],
        stop_loss=SLTPSpec(type="fixed_pct", value=5.0),
        take_profit=SLTPSpec(type="fixed_pct", value=10.0),
        risk_pct=1.0,
    )


def test_bearish_break_exit_closes_long_but_not_short():
    cfg = _cfg_with_direction_aware_exits()
    strat = ConfiguredStrategy(cfg)
    df = pd.DataFrame({
        "entry_bull_candle_break": [False],
        "entry_bear_candle_break": [True],
    })
    long_position = {"side": "long", "entry_price": 100.0}
    short_position = {"side": "short", "entry_price": 100.0}

    long_signal = strat.on_bar(df, 0, long_position)
    short_signal = strat.on_bar(df, 0, short_position)

    assert long_signal is not None and long_signal.action == "exit"
    assert short_signal is None


def test_bullish_break_exit_closes_short_but_not_long():
    cfg = _cfg_with_direction_aware_exits()
    strat = ConfiguredStrategy(cfg)
    df = pd.DataFrame({
        "entry_bull_candle_break": [True],
        "entry_bear_candle_break": [False],
    })
    long_position = {"side": "long", "entry_price": 100.0}
    short_position = {"side": "short", "entry_price": 100.0}

    long_signal = strat.on_bar(df, 0, long_position)
    short_signal = strat.on_bar(df, 0, short_position)

    assert long_signal is None
    assert short_signal is not None and short_signal.action == "exit"


def test_neither_break_fires_no_exit_for_either_side():
    cfg = _cfg_with_direction_aware_exits()
    strat = ConfiguredStrategy(cfg)
    df = pd.DataFrame({
        "entry_bull_candle_break": [False],
        "entry_bear_candle_break": [False],
    })
    assert strat.on_bar(df, 0, {"side": "long", "entry_price": 100.0}) is None
    assert strat.on_bar(df, 0, {"side": "short", "entry_price": 100.0}) is None


def test_exit_direction_none_still_applies_to_both_sides_unchanged():
    """Backward compatibility: a strategy that never sets exit_direction
    (every strategy saved before this feature existed) keeps the exact old
    behavior -- the SAME exit_conditions bucket, unconditionally AND-ed,
    applies to whichever side is open."""
    cfg = StrategyConfig(
        name="legacy exit test",
        timeframes={"entry": "1h"},
        concepts_used=["candle_break"],
        exit_conditions=[Condition(type="concept", name="candle_break", direction="bearish")],
        stop_loss=SLTPSpec(type="fixed_pct", value=5.0),
        take_profit=SLTPSpec(type="fixed_pct", value=10.0),
        risk_pct=1.0,
    )
    strat = ConfiguredStrategy(cfg)
    df = pd.DataFrame({"entry_bear_candle_break": [True]})
    long_signal = strat.on_bar(df, 0, {"side": "long", "entry_price": 100.0})
    short_signal = strat.on_bar(df, 0, {"side": "short", "entry_price": 100.0})
    assert long_signal is not None and long_signal.action == "exit"
    assert short_signal is not None and short_signal.action == "exit"
