"""Grand Feature Expansion, Phase 1 Feature 1: paper_trading/kill_switch.py
-- the global emergency-stop that halts ALL trading in one action.

Confirms it is genuinely stronger than the existing Start/Stop Engine
button: it is enforced at the trade-approval gate (risk_manager.evaluate),
blocks a fresh engine.start() until explicitly cleared, silences real
Telegram sends, and force-closes every open position when asked to.
"""

from unittest.mock import MagicMock, patch

import pytest

from data_engine import config as base_config, storage
from paper_trading import kill_switch, risk_manager


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


def test_kill_switch_defaults_to_inactive(test_db):
    assert kill_switch.is_active() is False
    s = kill_switch.status()
    assert s == {"active": False, "reason": None, "close_positions": False, "activated_at": None,
                 "activated_by": None, "deactivated_at": None, "deactivated_by": None, "activation_count": 0}


def test_activate_persists_state_and_stops_the_engine(test_db):
    from paper_trading.engine import engine as real_engine
    with patch.object(real_engine, "is_running", return_value=True), \
         patch.object(real_engine, "stop") as mock_stop:
        result = kill_switch.activate(reason="test emergency", actor="unit-test", close_positions=False)
    mock_stop.assert_called_once()
    assert result["ok"] is True
    assert result["engine_was_running"] is True
    s = kill_switch.status()
    assert s["active"] is True
    assert s["reason"] == "test emergency"
    assert s["activated_by"] == "unit-test"
    assert s["activation_count"] == 1


def test_activate_force_closes_every_open_position_when_asked(test_db):
    _open_position(id="p1", symbol="BTCUSDT")
    _open_position(id="p2", symbol="ETHUSDT")
    fake_client = MagicMock()
    fake_client.get_tickers.return_value = {
        "BTCUSDT": {"price": 105.0}, "ETHUSDT": {"price": 95.0},
    }
    with patch("data_engine.exchanges.registry.get_exchange_client", return_value=fake_client):
        result = kill_switch.activate(reason="test", close_positions=True)

    assert len(result["positions_closed"]) == 2
    assert storage.get_open_paper_positions() == []


def test_activate_with_close_positions_false_leaves_positions_open(test_db):
    _open_position(id="p1")
    result = kill_switch.activate(reason="test", close_positions=False)
    assert result["positions_closed"] == []
    assert len(storage.get_open_paper_positions()) == 1


def test_deactivate_clears_state_but_does_not_restart_the_engine(test_db):
    kill_switch.activate(reason="test", close_positions=False)
    from paper_trading.engine import engine as real_engine
    with patch.object(real_engine, "start") as mock_start:
        result = kill_switch.deactivate(actor="unit-test")
    mock_start.assert_not_called()
    assert result["ok"] is True
    s = kill_switch.status()
    assert s["active"] is False
    assert s["deactivated_by"] == "unit-test"


def test_deactivate_when_not_active_returns_an_error(test_db):
    result = kill_switch.deactivate()
    assert result["ok"] is False


def test_reactivating_increments_activation_count(test_db):
    kill_switch.activate(reason="first", close_positions=False)
    kill_switch.deactivate()
    kill_switch.activate(reason="second", close_positions=False)
    assert kill_switch.status()["activation_count"] == 2
    assert kill_switch.status()["reason"] == "second"


# ------------------------------------------------ enforcement at the gate

def test_risk_manager_refuses_every_trade_while_kill_switch_is_active(test_db):
    kill_switch.activate(reason="test", close_positions=False)
    candidate = {"stop_loss": 90.0, "entry_price": 100.0}
    approved, reason, size, risk_amount = risk_manager.evaluate(
        "strat1", "BTCUSDT", candidate, {"initial_balance": 10000.0, "risk_pct_default": 1.0},
    )
    assert approved is False
    assert "KILL SWITCH" in reason


def test_engine_start_refuses_while_kill_switch_is_active(test_db):
    from paper_trading.engine import PaperTradingEngine
    kill_switch.activate(reason="test", close_positions=False)
    fresh_engine = PaperTradingEngine()
    with pytest.raises(RuntimeError, match="[Kk]ill switch"):
        fresh_engine.start()
    assert fresh_engine.is_running() is False


def test_resume_engine_on_startup_stays_off_when_kill_switch_active(test_db):
    from paper_trading import config as pt_config, engine as engine_mod
    pt_config.update(engine_enabled=True)
    kill_switch.activate(reason="test", close_positions=False)
    with patch.object(engine_mod.engine, "start") as mock_start:
        engine_mod.resume_engine_on_startup()
    mock_start.assert_not_called()


def test_telegram_send_is_blocked_while_kill_switch_is_active(test_db):
    from paper_trading import telegram_bot
    _open_position(id="p1")
    kill_switch.activate(reason="test", close_positions=False)
    result = telegram_bot.send_signal_for_position("p1", trigger_type="manual")
    assert result["ok"] is False
    assert "kill switch" in result["error"].lower()
    # Logged as a failed attempt (success=0) -- list_telegram_signal_outcomes
    # deliberately excludes failed sends (see its own docstring), so check
    # the raw log instead.
    logged = storage.list_telegram_messages(limit=10)
    entry = next(r for r in logged if r["position_id"] == "p1")
    assert not entry["success"]
