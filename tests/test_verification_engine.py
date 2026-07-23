"""Phase 2 (BACKTESTING_MASTER_SPEC.md Requirement 12/13): the Backtest
Validation Engine and Strategy Verification Engine themselves need to be
trustworthy -- these tests feed each one both a clean case (must report
no issues) and a deliberately broken case (must catch it, not silently
pass), so a genuine regression in the verifier can't hide behind "it
never found anything wrong"."""

import pandas as pd
import pytest

from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from backtest_engine.configured_strategy import ConfiguredStrategy
from backtest_engine.engine import run_backtest
from backtest_engine import strategy_verifier, trade_validator
from backtest_engine.verification_engine import run_verification


def _make_df(rows):
    idx = pd.date_range("2026-01-01", periods=len(rows), freq="1min", tz="UTC")
    return pd.DataFrame({
        "open": [r[0] for r in rows], "high": [r[1] for r in rows],
        "low": [r[2] for r in rows], "close": [r[3] for r in rows],
        "volume": [100.0] * len(rows),
    }, index=idx)


# ------------------------------------------------------------ trade_validator

def _good_long_trade():
    return {
        "trade_num": 1, "side": "long", "entry_time": 0, "entry_price": 100.0,
        "exit_time": 60000, "exit_price": 95.0, "size": 10.0,
        "pnl": -50.0, "gross_pnl": -50.0, "commission_cost": 0.0,
        "exit_reason": "stop_loss", "stop_loss": 95.0, "take_profit": 110.0,
        "risk_amount": 50.0, "reward_amount": 100.0,
    }


def test_validator_passes_a_genuinely_correct_trade():
    issues = trade_validator.validate_trade(_good_long_trade())
    assert issues == []


def test_validator_catches_stop_loss_on_wrong_side_of_entry():
    bad = _good_long_trade()
    bad["stop_loss"] = 105.0  # ABOVE entry for a long -- impossible
    issues = trade_validator.validate_trade(bad)
    assert any("WRONG side" in i for i in issues)


def test_validator_catches_take_profit_on_wrong_side_of_entry():
    bad = _good_long_trade()
    bad["take_profit"] = 90.0  # BELOW entry for a long -- impossible
    issues = trade_validator.validate_trade(bad)
    assert any("WRONG side" in i for i in issues)


def test_validator_catches_stop_loss_exit_with_positive_gross_pnl():
    """The exact real bug class (structure SL landing on the wrong side of
    entry, mislabeling a win as a stop-loss loss) this module exists to
    catch if it were ever reintroduced."""
    bad = _good_long_trade()
    bad["gross_pnl"] = 25.0  # a "win" recorded as exit_reason=stop_loss
    issues = trade_validator.validate_trade(bad)
    assert any("can never be a gross win" in i for i in issues)


def test_validator_catches_impossible_position_size():
    bad = _good_long_trade()
    bad["size"] = -5.0
    issues = trade_validator.validate_trade(bad)
    assert any("impossible position size" in i for i in issues)


def test_validator_catches_pnl_sign_disagreeing_with_price_movement():
    bad = _good_long_trade()
    # Price moved DOWN for a long (a real loss) but gross_pnl claims positive.
    bad["gross_pnl"] = 25.0
    bad["exit_reason"] = "exit"  # avoid also tripping the stop_loss-specific check
    issues = trade_validator.validate_trade(bad)
    assert any("disagrees with entry/exit price movement" in i for i in issues)


def test_validator_catches_duplicate_trades_in_a_batch():
    t1 = _good_long_trade()
    t2 = dict(t1)
    t2["trade_num"] = 2
    result = trade_validator.validate_all_trades([t1, t2])
    assert result["pass"] is False
    assert len(result["duplicate_trades"]) == 1


def test_validator_batch_passes_when_every_trade_is_clean():
    t1 = _good_long_trade()
    t2 = _good_long_trade()
    t2["trade_num"] = 2
    t2["entry_time"] = 120000
    result = trade_validator.validate_all_trades([t1, t2])
    assert result["pass"] is True
    assert result["trade_count"] == 2


# ------------------------------------------------------------ strategy_verifier

def test_coverage_flags_a_raw_condition_as_skipped():
    cfg = StrategyConfig(
        name="t",
        entry_conditions=[Condition(type="raw", text="unrepresentable rule")],
    )
    findings = strategy_verifier.verify_rule_coverage(cfg, {})
    assert len(findings) == 1
    assert findings[0]["status"] == "SKIPPED"


def test_coverage_flags_a_never_reached_condition_due_to_and_short_circuit():
    """Second condition in an AND-gated list never gets a chance to run
    when the first is always false -- must show as SKIPPED, not silently
    invisible."""
    always_false = Condition(type="indicator_compare", indicator="rsi", op=">", value=999.0)
    never_reached = Condition(type="indicator_compare", indicator="rsi", op="<", value=50.0)
    cfg = StrategyConfig(
        name="t", indicators=[{"name": "rsi", "params": {"period": 14}, "role": None}],
        entry_conditions=[always_false, never_reached],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0), take_profit=SLTPSpec(type="fixed_pct", value=2.0),
        risk_pct=1.0,
    )
    strat = ConfiguredStrategy(cfg)
    counts = strategy_verifier.install_coverage_trace(strat)
    df = _make_df([(100, 101, 99, 100)] * 30)
    # Fake a plain rsi column so _eval has something to read without going
    # through the full concept/indicator prep pipeline.
    df["entry_rsi_14"] = 60.0
    df["close"] = df["close"]
    run_backtest(df, strat, {"initial_balance": 1000.0, "risk_pct": 1.0,
                              "commission_pct": 0.0, "slippage_pct": 0.0, "position_size_pct": 10.0})
    findings = strategy_verifier.verify_rule_coverage(cfg, counts)
    by_index = {f["index"]: f for f in findings}
    assert by_index[0]["status"] == "NEVER_TRUE"   # reached, always false
    assert by_index[1]["status"] == "SKIPPED"      # never reached at all


def test_coverage_reports_ok_for_a_genuinely_exercised_condition():
    cond = Condition(type="indicator_compare", indicator="rsi", op="<", value=999.0)  # always true
    cfg = StrategyConfig(
        name="t", indicators=[{"name": "rsi", "params": {"period": 14}, "role": None}],
        entry_conditions=[cond],
        stop_loss=SLTPSpec(type="fixed_pct", value=50.0), take_profit=SLTPSpec(type="fixed_pct", value=50.0),
        risk_pct=1.0,
    )
    strat = ConfiguredStrategy(cfg)
    counts = strategy_verifier.install_coverage_trace(strat)
    df = _make_df([(100, 101, 99, 100)] * 10)
    df["entry_rsi_14"] = 10.0
    run_backtest(df, strat, {"initial_balance": 1000.0, "risk_pct": 1.0,
                              "commission_pct": 0.0, "slippage_pct": 0.0, "position_size_pct": 10.0})
    findings = strategy_verifier.verify_rule_coverage(cfg, counts)
    assert findings[0]["status"] == "OK"


# ------------------------------------------------------------ verification_engine (integration)

def test_run_verification_end_to_end_pass_on_a_healthy_strategy():
    cond = Condition(type="indicator_compare", indicator="rsi", op="<", value=999.0)
    cfg = StrategyConfig(
        name="Healthy Test Strategy", timeframes={"entry": "1m"},
        indicators=[{"name": "rsi", "params": {"period": 14}, "role": None}],
        entry_conditions=[cond],
        stop_loss=SLTPSpec(type="fixed_pct", value=2.0), take_profit=SLTPSpec(type="fixed_pct", value=4.0),
        risk_pct=1.0,
    )
    df = _make_df([(100, 101, 99, 100)] * 20)
    df["entry_rsi_14"] = 10.0
    settings = {"initial_balance": 1000.0, "risk_pct": 1.0, "commission_pct": 0.0,
                "slippage_pct": 0.0, "position_size_pct": 10.0}
    report = run_verification(cfg, df, settings, symbol="TESTUSDT")
    assert report["overall_status"] == "PASS"
    assert report["rules_skipped"] == []
    assert report["trade_validation"]["pass"] is True
    stages = {e["stage"] for e in report["debug_log"]}
    assert {"strategy_loaded", "rule_loaded", "data_loaded", "results_generated"} <= stages


def test_run_verification_end_to_end_fail_on_a_raw_condition():
    cfg = StrategyConfig(
        name="Broken Test Strategy", timeframes={"entry": "1m"},
        entry_conditions=[Condition(type="raw", text="unrepresentable rule")],
        stop_loss=SLTPSpec(type="fixed_pct", value=2.0), take_profit=SLTPSpec(type="fixed_pct", value=4.0),
        risk_pct=1.0,
    )
    df = _make_df([(100, 101, 99, 100)] * 10)
    settings = {"initial_balance": 1000.0, "risk_pct": 1.0, "commission_pct": 0.0,
                "slippage_pct": 0.0, "position_size_pct": 10.0}
    report = run_verification(cfg, df, settings, symbol="TESTUSDT")
    assert report["overall_status"] == "FAIL"
    assert len(report["rules_skipped"]) == 1
