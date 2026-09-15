"""Phase 5 -- News Monitoring, wired into trading. Extends the existing
paper_trading.coin_event_caution module (Grand Master Batch, Phase 4 Item
12 -- built the CryptoPanic hook but never wired it into a trading
decision) with a cached gate wrapper (evaluate_for_risk_gate) and wires it
into risk_manager.evaluate() as a new, opt-in gate.

check_coin_caution() itself (the original Phase 4 function) is completely
untouched -- see tests/test_phase4_coin_event_caution.py for its own
coverage. These tests cover only the new caching layer and the new
risk_manager wiring.
"""

from unittest.mock import patch

import pytest
import requests

from data_engine import config as base_config, feature_toggles
from paper_trading import coin_event_caution, risk_manager


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    coin_event_caution._gate_cache.clear()
    yield


def test_default_toggle_is_off():
    assert feature_toggles.get_toggles()["coin_event_caution_gate_enabled"] is False


def test_no_api_key_passes_open():
    ok, reason = coin_event_caution.evaluate_for_risk_gate("BTCUSDT")
    assert ok is True and reason is None


def test_clear_result_passes_open():
    coin_event_caution.save_settings(cryptopanic_api_key="fake-key")
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"results": []}
        ok, reason = coin_event_caution.evaluate_for_risk_gate("BTCUSDT")
    assert ok is True and reason is None


def test_caution_result_blocks_with_the_real_headline_in_the_reason():
    coin_event_caution.save_settings(cryptopanic_api_key="fake-key")
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "results": [{"title": "Big exchange delisting rumor", "url": "https://x", "published_at": "2026-01-01"}],
        }
        ok, reason = coin_event_caution.evaluate_for_risk_gate("BTCUSDT")
    assert ok is False
    assert "Big exchange delisting rumor" in reason


def test_api_error_passes_open_never_fabricates_a_block():
    coin_event_caution.save_settings(cryptopanic_api_key="fake-key")
    with patch("requests.get", side_effect=requests.ConnectionError("network down")):
        ok, reason = coin_event_caution.evaluate_for_risk_gate("BTCUSDT")
    assert ok is True and reason is None


def test_result_is_cached_second_call_does_not_hit_network_again():
    coin_event_caution.save_settings(cryptopanic_api_key="fake-key")
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"results": []}
        coin_event_caution.evaluate_for_risk_gate("BTCUSDT")
        coin_event_caution.evaluate_for_risk_gate("BTCUSDT")
    assert mock_get.call_count == 1


def test_different_symbols_are_cached_independently():
    coin_event_caution.save_settings(cryptopanic_api_key="fake-key")
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"results": []}
        coin_event_caution.evaluate_for_risk_gate("BTCUSDT")
        coin_event_caution.evaluate_for_risk_gate("ETHUSDT")
    assert mock_get.call_count == 2


# --------------------------------------------------------------- risk_manager wiring

def _candidate():
    return {
        "direction": "bullish", "entry_price": 100.0, "stop_loss": 99.0, "take_profit": 104.0,
        "entry_reason": "test", "strategy_id": "stratX", "strategy_name": "stratX",
        "strategy_version": "v1", "lesson_ids": [], "timeframe": "1h", "stop_loss_type": "structure",
    }


SETTINGS = {"max_open_trades": 5, "initial_balance": 10000.0, "risk_pct_default": 1.0}


def test_evaluate_never_calls_the_gate_when_toggle_off(test_db, monkeypatch):
    def _boom(symbol):
        raise AssertionError("coin_event_caution must not be consulted when the toggle is off")
    monkeypatch.setattr(coin_event_caution, "evaluate_for_risk_gate", _boom)
    approved, reason, size, risk_amount = risk_manager.evaluate(
        "stratX", "BTCUSDT", _candidate(), SETTINGS, exchange="binance",
    )
    assert approved is True, reason


def test_evaluate_never_calls_the_gate_when_no_exchange_passed(test_db, monkeypatch):
    """Same backward-compatibility rule Phase 3.3 already established: a
    caller that never passes exchange= must behave exactly as before this
    feature existed."""
    feature_toggles.set_toggle("coin_event_caution_gate_enabled", True)
    def _boom(symbol):
        raise AssertionError("must not be consulted without an exchange")
    monkeypatch.setattr(coin_event_caution, "evaluate_for_risk_gate", _boom)
    approved, reason, size, risk_amount = risk_manager.evaluate("stratX", "BTCUSDT", _candidate(), SETTINGS)
    assert approved is True, reason


def test_evaluate_blocks_when_toggle_on_and_gate_is_negative(test_db, monkeypatch):
    feature_toggles.set_toggle("coin_event_caution_gate_enabled", True)
    monkeypatch.setattr(coin_event_caution, "evaluate_for_risk_gate", lambda symbol: (False, "fake caution reason"))
    approved, reason, size, risk_amount = risk_manager.evaluate(
        "stratX", "BTCUSDT", _candidate(), SETTINGS, exchange="binance",
    )
    assert approved is False
    assert reason == "fake caution reason"


def test_evaluate_approves_when_toggle_on_and_gate_is_clear(test_db, monkeypatch):
    feature_toggles.set_toggle("coin_event_caution_gate_enabled", True)
    monkeypatch.setattr(coin_event_caution, "evaluate_for_risk_gate", lambda symbol: (True, None))
    approved, reason, size, risk_amount = risk_manager.evaluate(
        "stratX", "BTCUSDT", _candidate(), SETTINGS, exchange="binance",
    )
    assert approved is True, reason
