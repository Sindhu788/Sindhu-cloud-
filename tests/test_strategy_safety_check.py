"""Automatic Strategy Safety Check: unit tests for each of the 3 checks
individually, PLUS integration tests proving the two real backtest entry
points (mtf_worker.run_one_symbol, verification_engine.run_verification)
actually REFUSE to run a backtest against a strategy that fails -- not
just that the check function itself returns the right verdict in
isolation. Every failing case here reproduces one of this project's real,
previously-confirmed bugs (Liquidity Sweep & FVG Validation Strategy's
duplicate exit clauses; Daily High-Low Liquidity Strategy's pdh/pdl
contradiction), so a regression here means a real bug becomes invisible
again, not just a hypothetical one.
"""

import pandas as pd
import pytest

from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from backtest_engine import strategy_safety_check as safety


def _passing_config():
    """A strategy shaped like the new EMA Trend-Pullback Strategy: clean
    entry/exit separation, no contradictions -- must pass every check."""
    return StrategyConfig(
        name="Clean Test Strategy", timeframes={"trend": "4h", "entry": "1h"},
        indicators=[{"name": "ema", "params": {"period": 50}, "role": "trend"},
                    {"name": "ema", "params": {"period": 20}, "role": "entry"}],
        long_entry_conditions=[
            Condition(type="price_compare", indicator="ema", params={"period": 50}, role="trend", op=">"),
            Condition(type="price_compare", indicator="ema", params={"period": 20}, role="entry", op=">"),
        ],
        short_entry_conditions=[
            Condition(type="price_compare", indicator="ema", params={"period": 50}, role="trend", op="<"),
            Condition(type="price_compare", indicator="ema", params={"period": 20}, role="entry", op="<"),
        ],
        exit_conditions=[],
        stop_loss=SLTPSpec(type="atr_multiple", value=1.5),
        take_profit=SLTPSpec(type="rr", value=2.0),
        risk_pct=1.0,
    )


def _duplicate_clause_config():
    """Reproduces Liquidity Sweep & FVG Validation Strategy's real bug:
    exit_conditions exactly duplicates 2 of 3 entry_conditions."""
    return StrategyConfig(
        name="Duplicate Exit Clause Test", timeframes={"entry": "15m", "analysis": "1h", "trend": "4h"},
        concepts_used=["support", "resistance", "fvg"],
        entry_conditions=[
            Condition(type="concept", name="resistance", direction="bearish"),
            Condition(type="concept", name="support", direction="bullish"),
            Condition(type="concept", name="fvg"),
        ],
        exit_conditions=[
            Condition(type="concept", name="support", direction="bullish"),
            Condition(type="concept", name="resistance", direction="bearish"),
        ],
        stop_loss=SLTPSpec(type="structure"), take_profit=SLTPSpec(type="structure"),
        risk_pct=1.0,
    )


def _contradictory_pdh_pdl_config():
    """Reproduces Daily High-Low Liquidity Strategy's real bug: bare pdh
    AND bare pdl required together in the same AND-gate."""
    return StrategyConfig(
        name="Contradictory PDH/PDL Test", timeframes={"entry": "5m", "analysis": "1h"},
        concepts_used=["pdh", "pdl"],
        entry_conditions=[
            Condition(type="concept", name="pdh", role="analysis"),
            Condition(type="concept", name="pdl", role="analysis"),
        ],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0), take_profit=SLTPSpec(type="fixed_pct", value=2.0),
        risk_pct=1.0,
    )


# ------------------------------------------------------------ Check 1

def test_check1_passes_clean_strategy():
    assert safety.check_duplicate_entry_exit_clauses(_passing_config()) == []


def test_check1_catches_duplicate_exit_clause():
    reasons = safety.check_duplicate_entry_exit_clauses(_duplicate_clause_config())
    assert len(reasons) == 2
    assert all("IDENTICAL" in r for r in reasons)


def test_check1_ignores_raw_conditions_never_evaluate_true_so_text_match_is_meaningless():
    """A raw (unparsed) condition never evaluates True in the engine, so
    two raw clauses with coincidentally-empty/equal signatures must NOT be
    flagged -- this was a real bug caught before finalizing (every raw
    condition previously collapsed to the same signature regardless of
    its actual text, producing false positives on unrelated clauses)."""
    cfg = StrategyConfig(
        name="Raw Clause Test",
        entry_conditions=[Condition(type="raw", text="price must move above the previous day's high")],
        exit_conditions=[Condition(type="raw", text="completely unrelated stop-loss placement rule")],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0), take_profit=SLTPSpec(type="fixed_pct", value=2.0),
        risk_pct=1.0,
    )
    assert safety.check_duplicate_entry_exit_clauses(cfg) == []


# ------------------------------------------------------------ Check 2

def test_check2_passes_clean_strategy_with_no_exit_conditions():
    assert safety.check_exit_gives_realistic_room(_passing_config()) == []


def test_check2_catches_exit_built_entirely_from_slow_level_concepts():
    reasons = safety.check_exit_gives_realistic_room(_duplicate_clause_config())
    assert any("slow-moving price-level concepts" in r for r in reasons)


def test_check2_catches_near_duplicate_different_threshold():
    cfg = StrategyConfig(
        name="Near Duplicate Test", timeframes={"entry": "1h"},
        indicators=[{"name": "rsi", "params": {"period": 14}, "role": "entry"}],
        entry_conditions=[Condition(type="indicator_compare", indicator="rsi", params={"period": 14},
                                     role="entry", op="<", value=30.0)],
        exit_conditions=[Condition(type="indicator_compare", indicator="rsi", params={"period": 14},
                                    role="entry", op="<", value=35.0)],  # same signal, different threshold
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0), take_profit=SLTPSpec(type="fixed_pct", value=2.0),
        risk_pct=1.0,
    )
    reasons = safety.check_exit_gives_realistic_room(cfg)
    assert any("SAME underlying signal" in r for r in reasons)


# ------------------------------------------------------------ Check 3

def test_check3_passes_clean_strategy():
    assert safety.check_contradictory_entry_gates(_passing_config()) == []


def test_check3_catches_pdh_pdl_contradiction():
    reasons = safety.check_contradictory_entry_gates(_contradictory_pdh_pdl_config())
    assert any("Impossible combination" in r and "pdh" in r and "pdl" in r for r in reasons)


def test_check3_catches_numeric_bound_contradiction_via_validator_reuse():
    cfg = StrategyConfig(
        name="RSI Contradiction Test", timeframes={"entry": "5m"},
        indicators=[{"name": "rsi", "params": {"period": 5}, "role": "entry"}],
        entry_conditions=[
            Condition(type="indicator_compare", indicator="rsi", params={"period": 5}, op="<", value=30.0),
            Condition(type="indicator_compare", indicator="rsi", params={"period": 5}, op=">", value=70.0),
        ],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0), take_profit=SLTPSpec(type="fixed_pct", value=2.0),
        risk_pct=1.0,
    )
    reasons = safety.check_contradictory_entry_gates(cfg)
    assert any("Impossible combination" in r for r in reasons)


# ------------------------------------------------------------ orchestrator

def test_run_safety_check_ready_on_clean_strategy():
    result = safety.run_safety_check(_passing_config())
    assert result == {"status": "ready", "passed": True, "reasons": []}


def test_run_safety_check_needs_review_on_duplicate_clause_bug():
    result = safety.run_safety_check(_duplicate_clause_config())
    assert result["status"] == "needs_review"
    assert result["passed"] is False
    assert len(result["reasons"]) >= 2


def test_run_safety_check_needs_review_on_contradiction_bug():
    result = safety.run_safety_check(_contradictory_pdh_pdl_config())
    assert result["status"] == "needs_review"
    assert any("pdh" in r and "pdl" in r for r in result["reasons"])


# ------------------------------------------------------------ wired into mtf_worker (integration)

def test_mtf_worker_refuses_to_backtest_a_strategy_that_fails_the_safety_check():
    from backtest_engine.mtf_worker import run_one_symbol
    settings = {"initial_balance": 1000.0, "risk_pct": 1.0, "commission_pct": 0.1,
                "slippage_pct": 0.05, "position_size_pct": 10.0}
    result = run_one_symbol(_duplicate_clause_config().to_dict(), "binance", "DOES_NOT_MATTER", settings, None, None)
    assert result["status"] == "error"
    assert result["stage"] == "safety_check"
    assert "safety check" in result["reason"].lower()
    assert result["trades"] == []


def test_mtf_worker_proceeds_normally_when_a_strategy_passes_the_safety_check():
    """A strategy that passes must reach a LATER stage than 'safety_check'
    -- since there's no real candle data for this fake symbol, it should
    fail at 'historical_data_loading', proving the safety-check gate let
    it through instead of blocking it."""
    from backtest_engine.mtf_worker import run_one_symbol
    settings = {"initial_balance": 1000.0, "risk_pct": 1.0, "commission_pct": 0.1,
                "slippage_pct": 0.05, "position_size_pct": 10.0}
    result = run_one_symbol(_passing_config().to_dict(), "binance", "DOES_NOT_EXIST_XYZ", settings, None, None)
    assert result["stage"] != "safety_check"


# ------------------------------------------------------------ wired into verification_engine (integration)

def test_verification_engine_refuses_to_backtest_a_strategy_that_fails_the_safety_check():
    from backtest_engine.verification_engine import run_verification
    idx = pd.date_range("2026-01-01", periods=50, freq="15min", tz="UTC")
    df = pd.DataFrame({"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 100.0}, index=idx)
    settings = {"initial_balance": 1000.0, "risk_pct": 1.0, "commission_pct": 0.0,
                "slippage_pct": 0.0, "position_size_pct": 10.0}
    report = run_verification(_duplicate_clause_config(), df, settings, symbol="TESTUSDT")
    assert report["overall_status"] == "FAIL"
    assert report["safety_check"]["passed"] is False
    assert report["trade_count"] == 0
    assert report["trades"] == []
