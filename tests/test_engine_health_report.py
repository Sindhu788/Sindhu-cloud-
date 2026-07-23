"""Final Audit: the Engine Health Report orchestrator (backtest_engine/
engine_health_report.py) and its new Statistics Verification section
(backtest_engine/statistics_verifier.py) need their own tests, same
principle as test_verification_engine.py -- prove they catch a genuinely
broken case, not just that they're silent on a clean one."""

import pandas as pd
import pytest

from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from backtest_engine import concepts, statistics_verifier
from backtest_engine.engine_health_report import run_engine_health_report
from backtest_engine.metrics import compute_metrics


def _make_df(rows):
    idx = pd.date_range("2026-01-01", periods=len(rows), freq="1min", tz="UTC")
    return pd.DataFrame({
        "open": [r[0] for r in rows], "high": [r[1] for r in rows],
        "low": [r[2] for r in rows], "close": [r[3] for r in rows],
        "volume": [100.0] * len(rows),
    }, index=idx)


def _random_walk_df(n=200, seed=3):
    import numpy as np
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC")
    close = 100 + rng.normal(0, 0.3, n).cumsum()
    open_ = close + rng.normal(0, 0.05, n)
    high = pd.Series(open_).combine(pd.Series(close), max) + abs(rng.normal(0, 0.15, n))
    low = pd.Series(open_).combine(pd.Series(close), min) - abs(rng.normal(0, 0.15, n))
    return pd.DataFrame({"open": open_, "high": high.values, "low": low.values, "close": close,
                          "volume": rng.uniform(50, 500, n)}, index=idx)


# ------------------------------------------------------------ statistics_verifier

def _trades_and_equity():
    trades = [
        {"pnl": 10.0}, {"pnl": -5.0}, {"pnl": 20.0}, {"pnl": -3.0},
    ]
    equity = [1000.0, 1010.0, 1005.0, 1025.0, 1022.0]
    return trades, equity


def test_statistics_verifier_passes_correctly_computed_metrics():
    trades, equity = _trades_and_equity()
    metrics = compute_metrics(trades, equity, 1000.0)
    issues = statistics_verifier.verify_statistics(trades, equity, 1000.0, metrics)
    assert issues == []


def test_statistics_verifier_catches_a_tampered_win_rate():
    trades, equity = _trades_and_equity()
    metrics = compute_metrics(trades, equity, 1000.0)
    metrics["win_rate"] = 99.9  # deliberately wrong
    issues = statistics_verifier.verify_statistics(trades, equity, 1000.0, metrics)
    assert any("win_rate" in i for i in issues)


def test_statistics_verifier_catches_net_profit_not_reconciling_with_balance():
    trades, equity = _trades_and_equity()
    metrics = compute_metrics(trades, equity, 1000.0)
    metrics["net_profit"] = 99999.0  # deliberately wrong -- doesn't match balance movement
    issues = statistics_verifier.verify_statistics(trades, equity, 1000.0, metrics)
    assert any("does not reconcile" in i or "net_profit" in i for i in issues)


# ------------------------------------------------------------ engine_health_report (integration)

def test_engine_health_report_end_to_end_pass_on_a_healthy_strategy():
    df = _random_walk_df(200)
    df["entry_rsi_14"] = concepts.rsi(df["close"], 14)
    cfg = StrategyConfig(
        name="Health Report Test", timeframes={"entry": "1m"},
        indicators=[{"name": "rsi", "params": {"period": 14}, "role": None}],
        entry_conditions=[Condition(type="indicator_compare", indicator="rsi", op="<", value=70.0)],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.5), take_profit=SLTPSpec(type="fixed_pct", value=3.0),
        risk_pct=1.0,
    )
    settings = {"initial_balance": 1000.0, "risk_pct": 1.0, "commission_pct": 0.1,
                "slippage_pct": 0.05, "position_size_pct": 10.0}
    report = run_engine_health_report(cfg, df, settings, symbol="TESTUSDT")

    assert report["overall_status"] == "PASS"
    for name, section in report["sections"].items():
        assert section["status"] in ("PASS", "not_run"), f"{name} unexpectedly {section['status']}: {section}"
    assert report["sections"]["data_verification"]["status"] == "not_run"  # no raw df supplied


def test_engine_health_report_data_verification_runs_and_passes_when_given_clean_data():
    df = _random_walk_df(150)
    df["entry_rsi_14"] = concepts.rsi(df["close"], 14)
    cfg = StrategyConfig(
        name="Health Report Data Test", timeframes={"entry": "1m"},
        indicators=[{"name": "rsi", "params": {"period": 14}, "role": None}],
        entry_conditions=[Condition(type="indicator_compare", indicator="rsi", op="<", value=999.0)],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.5), take_profit=SLTPSpec(type="fixed_pct", value=3.0),
        risk_pct=1.0,
    )
    settings = {"initial_balance": 1000.0, "risk_pct": 1.0, "commission_pct": 0.0,
                "slippage_pct": 0.0, "position_size_pct": 10.0}
    raw = df[["open", "high", "low", "close", "volume"]].copy()
    report = run_engine_health_report(cfg, df, settings, symbol="TESTUSDT",
                                       raw_entry_df=raw, entry_interval="1m")
    assert report["sections"]["data_verification"]["status"] == "PASS"


def test_engine_health_report_fails_overall_when_any_section_fails():
    cfg = StrategyConfig(
        name="Broken Health Report Test", timeframes={"entry": "1m"},
        entry_conditions=[Condition(type="raw", text="unrepresentable rule")],
        stop_loss=SLTPSpec(type="fixed_pct", value=2.0), take_profit=SLTPSpec(type="fixed_pct", value=4.0),
        risk_pct=1.0,
    )
    df = _make_df([(100, 101, 99, 100)] * 10)
    settings = {"initial_balance": 1000.0, "risk_pct": 1.0, "commission_pct": 0.0,
                "slippage_pct": 0.0, "position_size_pct": 10.0}
    report = run_engine_health_report(cfg, df, settings, symbol="TESTUSDT")
    assert report["overall_status"] == "FAIL"
    assert report["sections"]["strategy_verification"]["status"] == "FAIL"
