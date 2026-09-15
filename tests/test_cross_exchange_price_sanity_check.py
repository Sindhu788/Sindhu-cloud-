"""Grand Master Batch #2, Phase 4.7: real evidence for the Cross-Exchange
Price Sanity Check. Off by default (feature_toggles.
cross_exchange_sanity_check_enabled) -- these tests confirm both that the
check itself works correctly when exercised directly, AND that its
default-off wiring means send_signal_for_position() makes NO real network
call to a second exchange unless explicitly enabled (critical: every other
test in this suite that calls send_signal_for_position must never
accidentally trigger a live network call).
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from data_engine import config as base_config, feature_toggles, storage
from paper_trading import price_sanity_check, telegram_bot


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def test_default_toggle_is_off():
    assert feature_toggles.get_toggles()["cross_exchange_sanity_check_enabled"] is False


def test_passes_open_when_primary_price_is_none():
    ok, reason, secondary = price_sanity_check.cross_exchange_check("binance", "BTCUSDT", None)
    assert ok is True and reason is None and secondary is None


def test_passes_open_when_second_exchange_agrees(monkeypatch):
    fake_client = MagicMock()
    fake_client.get_tickers.return_value = {"BTCUSDT": {"price": 100.1}}
    monkeypatch.setattr(price_sanity_check, "get_exchange_client", lambda ex: fake_client)
    ok, reason, secondary = price_sanity_check.cross_exchange_check("binance", "BTCUSDT", 100.0, max_deviation_pct=1.0)
    assert ok is True and secondary == 100.1


def test_blocks_when_second_exchange_disagrees_significantly(monkeypatch):
    fake_client = MagicMock()
    fake_client.get_tickers.return_value = {"BTCUSDT": {"price": 105.0}}  # 5% off
    monkeypatch.setattr(price_sanity_check, "get_exchange_client", lambda ex: fake_client)
    ok, reason, secondary = price_sanity_check.cross_exchange_check("binance", "BTCUSDT", 100.0, max_deviation_pct=1.0)
    assert ok is False
    assert "bybit" in reason
    assert "glitch" in reason


def test_passes_open_when_second_exchange_has_no_data_for_the_symbol(monkeypatch):
    fake_client = MagicMock()
    fake_client.get_tickers.return_value = {}
    monkeypatch.setattr(price_sanity_check, "get_exchange_client", lambda ex: fake_client)
    ok, reason, secondary = price_sanity_check.cross_exchange_check("binance", "BTCUSDT", 100.0)
    assert ok is True and secondary is None


def test_passes_open_when_second_exchange_call_raises(monkeypatch):
    def _boom(ex):
        raise ConnectionError("network unreachable")
    monkeypatch.setattr(price_sanity_check, "get_exchange_client", _boom)
    ok, reason, secondary = price_sanity_check.cross_exchange_check("binance", "BTCUSDT", 100.0)
    assert ok is True and secondary is None


def _open_position(strategy_id="strat1"):
    pos = {
        "id": "posX", "exchange": "binance", "symbol": "ETHUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": int(datetime.now(timezone.utc).timestamp() * 1000),
        "created_at": "2026-01-01T00:00:00+00:00",
        "strategy_id": strategy_id, "strategy_name": "Test", "stop_loss": 90.0, "take_profit": 130.0,
    }
    storage.open_paper_position(pos)
    return pos


def test_send_signal_for_position_never_calls_the_second_exchange_by_default(test_db, monkeypatch):
    """The critical regression guard: this must NOT make a real network
    call (or even reach price_sanity_check at all) with the toggle at its
    default value, since dozens of OTHER tests in this suite call
    send_signal_for_position and must never be silently slowed down or
    made flaky by a live network dependency they don't expect."""
    _open_position()
    telegram_bot.save_settings(bot_token="x", channel_id="y", master_send_enabled=True)
    monkeypatch.setattr(telegram_bot, "_fetch_live_price", lambda *a, **k: None)
    with patch("paper_trading.price_sanity_check.cross_exchange_check") as mock_check:
        with patch.object(telegram_bot, "_raw_send", return_value=(True, None)):
            result = telegram_bot.send_signal_for_position("posX", trigger_type="manual")
    mock_check.assert_not_called()
    assert result["ok"] is True


def test_send_signal_for_position_uses_the_check_once_explicitly_enabled(test_db, monkeypatch):
    _open_position()
    telegram_bot.save_settings(bot_token="x", channel_id="y", master_send_enabled=True)
    feature_toggles.set_toggle("cross_exchange_sanity_check_enabled", True)
    monkeypatch.setattr(telegram_bot, "_fetch_live_price", lambda *a, **k: None)

    fake_client = MagicMock()
    fake_client.get_tickers.return_value = {"ETHUSDT": {"price": 300.0}}  # wildly off from entry_price=100
    monkeypatch.setattr(price_sanity_check, "get_exchange_client", lambda ex: fake_client)

    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        result = telegram_bot.send_signal_for_position("posX", trigger_type="manual")
    mock_send.assert_not_called()
    assert result["ok"] is False
    assert "glitch" in result["error"]
