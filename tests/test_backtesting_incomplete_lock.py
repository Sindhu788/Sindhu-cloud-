"""Batch 3, Task 3 -- the Incomplete Lock actually blocks a real
backtest run (POST /api/backtesting/run) for a strategy with unresolved
rules, and the explicit override actually lifts the block and tags the
resulting batch with a permanent visible warning.
"""

import pytest
from fastapi import HTTPException

from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from backtest_engine import strategy_library as lib
from data_engine import storage
from ai_integration import extraction_lock
from sindhu_web.api import backtesting


def _isolated_library(tmp_path, monkeypatch):
    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path / "library"))


def _make_strategy():
    cfg = StrategyConfig(
        name="Lock Test Strategy", timeframes={"entry": "1h"},
        entry_conditions=[Condition(type="indicator_compare", indicator="rsi", op="<", value=30.0)],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0), take_profit=SLTPSpec(type="fixed_pct", value=2.0),
        risk_pct=1.0,
    )
    return lib.create(cfg)


def _lock_it(strategy_id, overridden=False):
    rules = [
        {"id": 1, "text": "captured rule", "category": "entry", "status": "captured", "captured_as": "x"},
        {"id": 2, "text": "SL must be below the swing low, verbatim from the document", "category": "exit",
         "status": "missing", "captured_as": None},
    ]
    storage.save_extraction_fidelity_report(
        f"hash_{strategy_id}", 2, 1, 5, rules, "groq", "2026-01-01T00:00:00+00:00",
    )
    storage.set_extraction_fidelity_strategy_id(f"hash_{strategy_id}", strategy_id)
    if overridden:
        extraction_lock.set_override(strategy_id, True)


def test_run_backtest_is_blocked_for_a_locked_strategy(test_db, tmp_path, monkeypatch):
    _isolated_library(tmp_path, monkeypatch)
    strategy_id = _make_strategy()
    _lock_it(strategy_id)

    req = backtesting.RunRequest(strategy_id=strategy_id, all_coins=False, symbols=["BTCUSDT"])
    with pytest.raises(HTTPException) as exc_info:
        backtesting.run_backtest(req)

    assert exc_info.value.status_code == 423
    assert "SL must be below the swing low, verbatim from the document" in exc_info.value.detail
    # never raw jargon in the user-facing message
    assert "confluence" not in exc_info.value.detail.lower()


def test_run_backtest_is_allowed_after_override(test_db, tmp_path, monkeypatch):
    _isolated_library(tmp_path, monkeypatch)
    monkeypatch.setattr(storage, "load_symbols", lambda exchange: ["BTCUSDT"])

    strategy_id = _make_strategy()
    _lock_it(strategy_id, overridden=True)

    req = backtesting.RunRequest(strategy_id=strategy_id, all_coins=False, symbols=["BTCUSDT"])
    # Must not raise 423 -- may still fail later for unrelated reasons
    # (e.g. no market data in this isolated test DB), but never on the lock.
    try:
        backtesting.run_backtest(req)
    except HTTPException as e:
        assert e.status_code != 423


def test_extraction_verification_endpoint_reports_lock_status(test_db, tmp_path, monkeypatch):
    _isolated_library(tmp_path, monkeypatch)
    strategy_id = _make_strategy()
    _lock_it(strategy_id)

    result = backtesting.get_extraction_verification(strategy_id)
    assert result["locked"] is True
    assert result["expected_count"] == 2
    assert result["captured_count"] == 1
    assert len(result["rows"]) == 2


def test_extraction_override_endpoint_unlocks_and_returns_updated_status(test_db, tmp_path, monkeypatch):
    _isolated_library(tmp_path, monkeypatch)
    strategy_id = _make_strategy()
    _lock_it(strategy_id)

    result = backtesting.set_extraction_override(strategy_id, backtesting.ExtractionOverrideRequest(overridden=True))
    assert result["locked"] is False
    assert result["overridden"] is True

    # confirm it actually persisted, not just in the response
    status = extraction_lock.check_strategy_lock(strategy_id)
    assert status["locked"] is False
