"""Grand Feature Expansion, Phase 1 Feature 5: Account-wide Drawdown
Circuit-Breaker (paper_trading/account_drawdown_guard.py) -- distinct from
the existing per-strategy drawdown_guard.py: this compares the COMBINED
balance across every book against its own all-time peak and blocks new
entries for EVERY strategy at once, while leaving open positions and
per-strategy pauses completely untouched.
"""

from data_engine import config as base_config, storage
from paper_trading import account_drawdown_guard, config as pt_config, risk_manager

import pytest


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _open_position(**overrides):
    pos = {
        "id": "pos1", "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": 1700000000000, "created_at": "2026-01-01T00:00:00+00:00",
        "strategy_id": "strat1", "strategy_name": "Test Strategy",
    }
    pos.update(overrides)
    storage.open_paper_position(pos)
    return pos


def _close(position_id, pnl, pnl_pct=None, closed_at="2026-01-02T00:00:00+00:00"):
    pnl_pct = pnl_pct if pnl_pct is not None else (pnl / 1000.0 * 100)
    storage.close_paper_position(
        position_id, 100.0 + pnl, 1700000100000, pnl, pnl_pct,
        "take_profit" if pnl >= 0 else "stop_loss", {}, {}, closed_at,
    )


def test_default_initial_balance_is_10000():
    assert pt_config.load()["initial_balance"] == 10000.0
    assert pt_config.load()["account_drawdown_pause_pct_threshold"] == 20.0


def test_status_before_any_trade_reports_zero_drawdown(test_db):
    s = account_drawdown_guard.status()
    assert s["paused"] is False
    assert s["drawdown_pct"] == 0.0


def test_evaluate_account_does_not_pause_below_threshold(test_db):
    _open_position(id="p1")
    account_drawdown_guard.evaluate_account()  # seeds the peak at 10000, before any realized pnl
    _close("p1", pnl=-1000.0)  # 10% of a single 10000 book -- below the 20% default
    reason = account_drawdown_guard.evaluate_account()
    assert reason is None
    assert account_drawdown_guard.is_globally_paused() is False


def test_evaluate_account_pauses_when_threshold_crossed(test_db):
    _open_position(id="p1")
    account_drawdown_guard.evaluate_account()  # seeds the peak at 10000, before any realized pnl
    _close("p1", pnl=-3000.0)  # 30% of a single 10000 book -- above the 20% default
    reason = account_drawdown_guard.evaluate_account()
    assert reason is not None
    assert "30.0%" in reason
    assert account_drawdown_guard.is_globally_paused() is True
    s = account_drawdown_guard.status()
    assert s["paused"] is True
    assert s["paused_reason"] == reason


def test_peak_tracks_new_highs_before_computing_drawdown(test_db):
    _open_position(id="p1")
    _close("p1", pnl=2000.0)  # new peak: 12000
    assert account_drawdown_guard.evaluate_account() is None
    _open_position(id="p2")
    _close("p2", pnl=-3000.0)  # now at 9000: drawdown from the 12000 peak, not the original 10000
    reason = account_drawdown_guard.evaluate_account()
    assert reason is not None
    assert "25.0%" in reason  # (12000-9000)/12000 = 25%


def test_does_not_retrigger_or_overwrite_reason_once_already_paused(test_db):
    _open_position(id="p1")
    account_drawdown_guard.evaluate_account()  # seeds the peak
    _close("p1", pnl=-3000.0)
    first_reason = account_drawdown_guard.evaluate_account()
    assert first_reason is not None
    # A further loss while already paused must not change the recorded reason.
    _open_position(id="p2", strategy_id="strat2")
    _close("p2", pnl=-500.0)
    assert account_drawdown_guard.evaluate_account() is None
    assert account_drawdown_guard.status()["paused_reason"] == first_reason


def test_resume_account_clears_the_pause(test_db):
    _open_position(id="p1")
    account_drawdown_guard.evaluate_account()  # seeds the peak
    _close("p1", pnl=-3000.0)
    account_drawdown_guard.evaluate_account()
    assert account_drawdown_guard.is_globally_paused() is True

    account_drawdown_guard.resume_account(actor="unit-test")
    assert account_drawdown_guard.is_globally_paused() is False


def test_risk_manager_blocks_every_book_while_globally_paused(test_db):
    _open_position(id="p1")
    account_drawdown_guard.evaluate_account()  # seeds the peak
    _close("p1", pnl=-3000.0)
    account_drawdown_guard.evaluate_account()

    candidate = {"stop_loss": 90.0, "entry_price": 100.0}
    # A DIFFERENT strategy's book is blocked too -- this is a system-wide gate.
    approved, reason, size, risk_amount = risk_manager.evaluate(
        "some_other_strategy", "ETHUSDT", candidate, {"initial_balance": 10000.0, "risk_pct_default": 1.0},
    )
    assert approved is False
    assert "drawdown circuit-breaker" in reason


def test_pause_and_resume_are_recorded_in_the_permanent_audit_trail(test_db):
    _open_position(id="p1")
    account_drawdown_guard.evaluate_account()  # seeds the peak
    _close("p1", pnl=-3000.0)
    account_drawdown_guard.evaluate_account()
    account_drawdown_guard.resume_account(actor="unit-test")

    audit = storage.list_audit_trail(entity="account_drawdown")
    actions = {r["action"] for r in audit}
    assert actions == {"paused", "resumed"}
