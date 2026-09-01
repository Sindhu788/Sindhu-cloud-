"""candle_body_pct only ever supported a MINIMUM body-size threshold ("a
strong candle"). Lower Time Frame Liquidity Reversal's "exhaustion candle"
(small body, long wick, body <= 30% of the full range) needs the mirror
maximum bound -- confirmed missing by that strategy's Part 1 capability
check, fixed by mirroring candle_range_pct's existing min/max shape."""

import pandas as pd

from backtest_engine.strategy_config import StrategyConfig, Condition
from backtest_engine.configured_strategy import ConfiguredStrategy


def _strat():
    return ConfiguredStrategy(StrategyConfig(name="body pct max test", timeframes={"entry": "1h"}))


def test_max_pct_accepts_small_body_exhaustion_candle():
    strat = _strat()
    # open=100, close=100.5, high=110, low=100 -> body=0.5, range=10 -> body_pct=5%
    df = pd.DataFrame({"open": [100.0], "high": [110.0], "low": [100.0], "close": [100.5]})
    cond = Condition(type="candle_body_pct", params={"max_pct": 30})
    assert strat._eval(cond, df, 0) is True


def test_max_pct_rejects_large_body_candle():
    strat = _strat()
    # open=100, close=109, high=110, low=100 -> body=9, range=10 -> body_pct=90%
    df = pd.DataFrame({"open": [100.0], "high": [110.0], "low": [100.0], "close": [109.0]})
    cond = Condition(type="candle_body_pct", params={"max_pct": 30})
    assert strat._eval(cond, df, 0) is False


def test_min_and_max_together_bound_a_range():
    strat = _strat()
    # body_pct = 50%
    df = pd.DataFrame({"open": [100.0], "high": [110.0], "low": [100.0], "close": [105.0]})
    inside = Condition(type="candle_body_pct", params={"min_pct": 40, "max_pct": 60})
    too_strict_low = Condition(type="candle_body_pct", params={"min_pct": 60})
    too_strict_high = Condition(type="candle_body_pct", params={"max_pct": 40})
    assert strat._eval(inside, df, 0) is True
    assert strat._eval(too_strict_low, df, 0) is False
    assert strat._eval(too_strict_high, df, 0) is False


def test_min_pct_only_backward_compatible_unchanged():
    strat = _strat()
    df = pd.DataFrame({"open": [100.0], "high": [110.0], "low": [100.0], "close": [109.0]})
    cond = Condition(type="candle_body_pct", params={"min_pct": 50})
    assert strat._eval(cond, df, 0) is True
