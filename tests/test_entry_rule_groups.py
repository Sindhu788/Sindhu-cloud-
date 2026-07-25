"""entry_rule_groups: branching/conditional entry logic (N independent
alternative entry paths, OR'd against each other, each internally AND'd)
-- the schema gap found via a real import (PBD Volume Profile Strategy,
whose P/B/D-shape entry rules are 4 genuinely alternative long setups that
long_entry_conditions' single AND-gate could not represent, so the AI
came back with entry_conditions: 0 despite the source text clearly having
entry rules)."""

import pandas as pd
import pytest

from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from backtest_engine.configured_strategy import ConfiguredStrategy
from backtest_engine.engine import run_backtest
from backtest_engine import validator, strategy_safety_check as safety


def _make_df(rows):
    idx = pd.date_range("2026-01-01", periods=len(rows), freq="1min", tz="UTC")
    return pd.DataFrame({
        "open": [r[0] for r in rows], "high": [r[1] for r in rows],
        "low": [r[2] for r in rows], "close": [r[3] for r in rows],
        "volume": [100.0] * len(rows),
    }, index=idx)


def _rsi_group_config():
    """Two alternative bullish paths (either low RSI OR high RSI, an
    artificial but clean way to prove OR-across-groups) and one bearish
    path -- mirrors the shape of PBD's P/B/D branching."""
    return StrategyConfig(
        name="Rule Group Test", timeframes={"entry": "1m"},
        indicators=[{"name": "rsi", "params": {"period": 14}, "role": None}],
        entry_rule_groups=[
            {"label": "Oversold Bounce", "direction": "bullish",
             "conditions": [Condition(type="indicator_compare", indicator="rsi", op="<", value=20.0)]},
            {"label": "Momentum Continuation", "direction": "bullish",
             "conditions": [Condition(type="indicator_compare", indicator="rsi", op=">", value=90.0)]},
            {"label": "Overbought Fade", "direction": "bearish",
             "conditions": [Condition(type="indicator_compare", indicator="rsi", op=">", value=95.0)]},
        ],
        stop_loss=SLTPSpec(type="fixed_pct", value=2.0), take_profit=SLTPSpec(type="fixed_pct", value=4.0),
        risk_pct=1.0,
    )


def test_first_matching_group_fires_long():
    cfg = _rsi_group_config()
    strat = ConfiguredStrategy(cfg)
    df = _make_df([(100, 101, 99, 100)] * 5)
    df["entry_rsi_14"] = 10.0  # only the "Oversold Bounce" group's condition is true
    signal = strat.on_bar(strat.prepare(df), 4, None)
    assert signal is not None and signal.action == "buy"


def test_second_group_fires_when_first_does_not():
    cfg = _rsi_group_config()
    strat = ConfiguredStrategy(cfg)
    df = _make_df([(100, 101, 99, 100)] * 5)
    df["entry_rsi_14"] = 92.0  # "Oversold Bounce" false, "Momentum Continuation" true
    signal = strat.on_bar(strat.prepare(df), 4, None)
    assert signal is not None and signal.action == "buy"


def test_contradictory_bar_both_directions_match_yields_no_signal():
    cfg = _rsi_group_config()
    strat = ConfiguredStrategy(cfg)
    df = _make_df([(100, 101, 99, 100)] * 5)
    df["entry_rsi_14"] = 96.0  # RSI > 90 (bullish group #2) AND RSI > 95 (bearish group) both true
    signal = strat.on_bar(strat.prepare(df), 4, None)
    assert signal is None


def test_no_group_matches_yields_no_signal():
    cfg = _rsi_group_config()
    strat = ConfiguredStrategy(cfg)
    df = _make_df([(100, 101, 99, 100)] * 5)
    df["entry_rsi_14"] = 50.0
    signal = strat.on_bar(strat.prepare(df), 4, None)
    assert signal is None


def test_entry_rule_groups_takes_priority_over_legacy_entry_conditions():
    """A strategy with BOTH entry_rule_groups and a (contradictory)
    entry_conditions populated must use entry_rule_groups exclusively --
    proves the priority order documented in on_bar()."""
    cfg = _rsi_group_config()
    cfg.entry_conditions = [Condition(type="indicator_compare", indicator="rsi", op="<", value=1.0)]  # never true
    strat = ConfiguredStrategy(cfg)
    df = _make_df([(100, 101, 99, 100)] * 5)
    df["entry_rsi_14"] = 10.0
    signal = strat.on_bar(strat.prepare(df), 4, None)
    assert signal is not None  # fired via entry_rule_groups, not the impossible entry_conditions


def test_full_backtest_runs_and_produces_trades_via_rule_groups():
    cfg = _rsi_group_config()
    strat = ConfiguredStrategy(cfg)
    rows = [(100, 101, 99, 100)] * 3 + [(100, 101, 99, 100)] * 20
    df = _make_df(rows)
    df["entry_rsi_14"] = [50.0] * 3 + [10.0] * 20  # oversold bounce fires from bar 3 onward
    settings = {"initial_balance": 1000.0, "risk_pct": 1.0, "commission_pct": 0.0,
                "slippage_pct": 0.0, "position_size_pct": 10.0}
    trades, equity, balance = run_backtest(df, strat, settings)
    assert len(trades) >= 1
    assert trades[0]["side"] == "long"


# ------------------------------------------------------------ validator

def test_validator_flags_empty_group_and_bad_direction():
    cfg = StrategyConfig(
        name="Bad Group Test", timeframes={"entry": "1m"},
        entry_rule_groups=[
            {"label": "Empty Group", "direction": "bullish", "conditions": []},
            {"label": "Bad Direction", "direction": "sideways", "conditions": [
                Condition(type="indicator_compare", indicator="rsi", op="<", value=30.0)]},
        ],
        indicators=[{"name": "rsi", "params": {"period": 14}, "role": None}],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0), take_profit=SLTPSpec(type="fixed_pct", value=2.0),
        risk_pct=1.0,
    )
    errors = validator.validate(cfg)
    assert any("no conditions" in e for e in errors)
    assert any("must be 'bullish' or 'bearish'" in e for e in errors)


def test_validator_accepts_a_clean_rule_group_strategy():
    cfg = _rsi_group_config()
    errors = validator.validate(cfg)
    assert errors == []


# ------------------------------------------------------------ strategy_safety_check

def test_safety_check_sees_entry_rule_groups_conditions():
    """Exit condition duplicating a rule-group's condition must still be
    caught -- entry_rule_groups is a real entry bucket for this check."""
    cfg = _rsi_group_config()
    cfg.exit_conditions = [Condition(type="indicator_compare", indicator="rsi", op="<", value=20.0)]  # dup of group 1
    result = safety.run_safety_check(cfg)
    assert result["passed"] is False
    assert any("entry_rule_groups" in r for r in result["reasons"])
