"""backtest_engine.strategy_parser._ensure_indicators_for_conditions:
real bug found via a full-library backtest run (Five A+ iFVG Setups had
indicators=[] with a price_compare condition referencing vwap -- the
column was never computed, so "price < vwap" silently evaluated False on
all 60,996 bars it was checked across a full year of real BTCUSDT data).

A second, related bug found while investigating: the backfill for
indicator_compare/price_compare conditions always registered the new
entry under role=None, ignoring the condition's own declared role --
harmless when a name+period fallback match already exists elsewhere in
`indicators` (found live on 3 other strategies, all still correctly
executing), but wrong bookkeeping regardless, and the one thing standing
between "an indicator with no declaration under ANY role" and getting
caught at all.
"""

from backtest_engine.strategy_config import StrategyConfig, Condition
from backtest_engine.strategy_parser import _ensure_indicators_for_conditions


def test_price_compare_with_undeclared_indicator_gets_backfilled():
    """The exact real defect: a price_compare condition referencing an
    indicator that was never declared anywhere in config.indicators."""
    cfg = StrategyConfig(
        name="VWAP Test", timeframes={"entry": "1m"}, indicators=[],
        entry_conditions=[Condition(type="price_compare", indicator="vwap", op="<")],
    )
    _ensure_indicators_for_conditions(cfg)
    assert {"name": "vwap", "params": {}, "role": None} in cfg.indicators


def test_backfill_respects_the_condition_role_not_a_hardcoded_none():
    """A condition declaring role="trend" must be backfilled under
    role="trend", not role=None -- registering the wrong role is
    harmless ONLY when a separate correctly-tagged entry already exists
    (the name+period fallback in _indicator_column then still finds it);
    when it's the ONLY entry, a role=None backfill would leave the
    condition's own role="trend" lookup unresolved."""
    cfg = StrategyConfig(
        name="Role Test", timeframes={"trend": "4h", "entry": "1h"}, indicators=[],
        entry_conditions=[
            Condition(type="price_compare", indicator="ema", params={"period": 50}, role="trend", op=">"),
        ],
    )
    _ensure_indicators_for_conditions(cfg)
    assert {"name": "ema", "params": {"period": 50}, "role": "trend"} in cfg.indicators
    assert {"name": "ema", "params": {"period": 50}, "role": None} not in cfg.indicators


def test_already_declared_indicator_is_not_duplicated():
    cfg = StrategyConfig(
        name="No Dup Test", timeframes={"entry": "1h"},
        indicators=[{"name": "rsi", "params": {"period": 14}, "role": None}],
        entry_conditions=[Condition(type="indicator_compare", indicator="rsi", params={"period": 14}, op="<", value=30.0)],
    )
    _ensure_indicators_for_conditions(cfg)
    assert cfg.indicators == [{"name": "rsi", "params": {"period": 14}, "role": None}]


def test_indicator_vs_indicator_still_registers_both_sides_by_role():
    """Unaffected by this fix -- already passed cond.role before, still
    does, both indicator and indicator2 sides."""
    cfg = StrategyConfig(
        name="Cross Test", timeframes={"entry": "1h"}, indicators=[],
        entry_conditions=[
            Condition(type="indicator_vs_indicator", indicator="ema", params={"period": 20}, role="entry",
                      op=">", indicator2="ema", params2={"period": 50}),
        ],
    )
    _ensure_indicators_for_conditions(cfg)
    assert {"name": "ema", "params": {"period": 20}, "role": "entry"} in cfg.indicators
    assert {"name": "ema", "params": {"period": 50}, "role": "entry"} in cfg.indicators
