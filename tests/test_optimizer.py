"""automation_pipeline.optimizer.tunable_dimensions(): real bug found live
via a Walk-Forward Test run on EMA Trend-Pullback Strategy. Its `_apply`
closure for an indicator's period dimension mutated ONLY
config.indicators[idx]["params"]["period"], never the Condition objects
that reference that indicator with their OWN explicit params={"period":
N} (the pattern price_compare/indicator_compare conditions actually use).
ConfiguredStrategy._indicator_column() resolves a column using the
CONDITION's own params first -- so every period-varied candidate for
such a strategy silently pointed at a column that was never computed,
producing 0 trades for EVERY candidate on that dimension (confirmed
live: 20/20 EMA period candidates showed "0 trades" before this fix,
while the untouched ATR/take-profit/risk dimensions worked normally).
This is exactly the kind of silent wrong-result bug the automatic safety
check/verification tooling built earlier this session can't catch,
because nothing here is "invalid" -- the candidate configs are
structurally fine, they just can never produce a signal.
"""

from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from automation_pipeline.optimizer import tunable_dimensions


def _ema_trend_pullback_style_config():
    """Mirrors EMA Trend-Pullback Strategy's real shape: conditions carry
    their OWN explicit period in params, not relying on a bare
    name+role lookup into config.indicators."""
    return StrategyConfig(
        name="Optimizer Period-Sync Test", timeframes={"trend": "4h", "entry": "1h"},
        indicators=[
            {"name": "ema", "params": {"period": 50}, "role": "trend"},
            {"name": "ema", "params": {"period": 20}, "role": "entry"},
        ],
        long_entry_conditions=[
            Condition(type="price_compare", indicator="ema", params={"period": 50}, role="trend", op=">"),
            Condition(type="price_compare", indicator="ema", params={"period": 20}, role="entry", op=">"),
        ],
        short_entry_conditions=[
            Condition(type="price_compare", indicator="ema", params={"period": 50}, role="trend", op="<"),
            Condition(type="price_compare", indicator="ema", params={"period": 20}, role="entry", op="<"),
        ],
        stop_loss=SLTPSpec(type="atr_multiple", value=1.5), take_profit=SLTPSpec(type="rr", value=2.0),
        risk_pct=1.0,
    )


def test_applying_a_period_candidate_updates_the_referencing_conditions_too():
    cfg = _ema_trend_pullback_style_config()
    dims = tunable_dimensions(cfg)

    trend_ema_dim = next(d for d in dims if d["id"] == "indicator_ema_0_period")
    assert trend_ema_dim["baseline"] == 50

    candidate = _ema_trend_pullback_style_config()
    trend_ema_dim_for_candidate = next(d for d in tunable_dimensions(candidate) if d["id"] == "indicator_ema_0_period")
    trend_ema_dim_for_candidate["apply"](candidate, 30)

    # The indicators-list entry changed (pre-existing behavior).
    assert candidate.indicators[0]["params"]["period"] == 30
    # The CONDITIONS that reference it (role="trend") must ALSO have
    # changed to 30 -- this is the actual fix. The entry-role ema (period
    # 20, a DIFFERENT role) must be completely untouched.
    long_trend_cond = candidate.long_entry_conditions[0]
    long_entry_cond = candidate.long_entry_conditions[1]
    short_trend_cond = candidate.short_entry_conditions[0]
    assert long_trend_cond.role == "trend" and long_trend_cond.params["period"] == 30
    assert short_trend_cond.role == "trend" and short_trend_cond.params["period"] == 30
    assert long_entry_cond.role == "entry" and long_entry_cond.params["period"] == 20  # untouched


def test_applying_the_entry_role_period_does_not_affect_the_trend_role_condition():
    cfg = _ema_trend_pullback_style_config()
    entry_ema_dim = next(d for d in tunable_dimensions(cfg) if d["id"] == "indicator_ema_1_period")
    assert entry_ema_dim["baseline"] == 20

    candidate = _ema_trend_pullback_style_config()
    entry_ema_dim_for_candidate = next(d for d in tunable_dimensions(candidate) if d["id"] == "indicator_ema_1_period")
    entry_ema_dim_for_candidate["apply"](candidate, 12)

    assert candidate.indicators[1]["params"]["period"] == 12
    assert candidate.long_entry_conditions[1].params["period"] == 12  # entry-role, changed
    assert candidate.long_entry_conditions[0].params["period"] == 50  # trend-role, untouched


def test_entry_rule_groups_conditions_are_also_kept_in_sync():
    cfg = StrategyConfig(
        name="Rule Group Period-Sync Test", timeframes={"trend": "4h", "entry": "1h"},
        indicators=[{"name": "ema", "params": {"period": 50}, "role": "trend"}],
        entry_rule_groups=[
            {"label": "Bull", "direction": "bullish",
             "conditions": [Condition(type="price_compare", indicator="ema", params={"period": 50},
                                       role="trend", op=">")]},
        ],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0), take_profit=SLTPSpec(type="rr", value=2.0),
        risk_pct=1.0,
    )
    dim = next(d for d in tunable_dimensions(cfg) if d["id"] == "indicator_ema_0_period")
    dim["apply"](cfg, 35)
    assert cfg.entry_rule_groups[0]["conditions"][0].params["period"] == 35


def test_indicator_vs_indicator_both_sides_stay_in_sync_independently():
    cfg = StrategyConfig(
        name="Cross Period-Sync Test", timeframes={"entry": "1h"},
        indicators=[
            {"name": "ema", "params": {"period": 20}, "role": "entry"},
            {"name": "ema", "params": {"period": 50}, "role": "entry"},
        ],
        entry_conditions=[
            Condition(type="indicator_vs_indicator", indicator="ema", params={"period": 20}, role="entry",
                      op=">", indicator2="ema", params2={"period": 50}),
        ],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0), take_profit=SLTPSpec(type="rr", value=2.0),
        risk_pct=1.0,
    )
    fast_dim = next(d for d in tunable_dimensions(cfg) if d["id"] == "indicator_ema_0_period")
    fast_dim["apply"](cfg, 12)
    cond = cfg.entry_conditions[0]
    assert cond.params["period"] == 12   # the "fast" side changed
    assert cond.params2["period"] == 50  # the "slow" side (indicator2) untouched
