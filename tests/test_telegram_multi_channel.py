"""Grand Feature Expansion, Phase 2 Feature 22: Multi-Channel Support --
different strategies' real-time signals can be routed to different
Telegram channels, using the SAME bot token (not a second set of
credentials). A strategy with no configured override keeps going to the
one default channel_id, exactly as before this feature.
"""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from data_engine import config as base_config, storage
from paper_trading import telegram_bot


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


@pytest.fixture(autouse=True)
def no_real_live_price(monkeypatch):
    monkeypatch.setattr(telegram_bot, "_fetch_live_price", lambda *a, **k: None)


def _open_position(**overrides):
    pos = {
        "id": "pos1", "strategy_id": "strat1", "strategy_name": "Test Strategy",
        "symbol": "BTCUSDT", "direction": "long", "entry_price": 100.0,
        "stop_loss": 95.0, "take_profit": 110.0, "market_state": "trending_up",
        "session": "london", "entry_reason": "test",
        "exchange": "binance", "size": 1.0, "risk_amount": 5.0,
        "entry_time": int(datetime.now(timezone.utc).timestamp() * 1000),
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    pos.update(overrides)
    storage.open_paper_position(pos)
    return pos


def _configure():
    telegram_bot.save_settings(bot_token="dummy", channel_id="default_channel")


def test_channel_for_strategy_is_none_when_no_override_configured(test_db):
    _configure()
    assert telegram_bot.channel_for_strategy("strat1") is None


def test_set_and_clear_a_channel_override(test_db):
    _configure()
    overrides = telegram_bot.set_strategy_channel_override("strat1", "channel_A")
    assert overrides == {"strat1": "channel_A"}
    assert telegram_bot.channel_for_strategy("strat1") == "channel_A"
    assert telegram_bot.channel_for_strategy("strat2") is None  # a different strategy is unaffected

    telegram_bot.set_strategy_channel_override("strat1", None)
    assert telegram_bot.channel_for_strategy("strat1") is None


def test_a_strategy_with_no_override_sends_to_the_default_channel(test_db):
    _open_position()
    _configure()
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        telegram_bot.send_signal_for_position("pos1", trigger_type="manual")
    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs["channel_id_override"] is None


def test_a_strategy_with_an_override_sends_to_its_own_channel(test_db):
    _open_position(strategy_id="strat1")
    _configure()
    telegram_bot.set_strategy_channel_override("strat1", "channel_A")
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        telegram_bot.send_signal_for_position("pos1", trigger_type="manual")
    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs["channel_id_override"] == "channel_A"


def test_raw_send_actually_targets_the_overridden_channel(test_db, monkeypatch):
    """One level deeper than the mocked test above: proves the override
    genuinely reaches the outbound HTTP call's chat_id, not just that it
    was passed as a kwarg somewhere."""
    _configure()
    captured = {}

    class _FakeResponse:
        status_code = 200
        def json(self):
            return {"ok": True}

    def _fake_post(url, json, timeout, proxies):
        captured["chat_id"] = json["chat_id"]
        return _FakeResponse()

    monkeypatch.setattr(telegram_bot.requests, "post", _fake_post)
    telegram_bot._raw_send("hello", channel_id_override="channel_A")
    assert captured["chat_id"] == "channel_A"


def test_close_followup_also_routes_to_the_strategy_override(test_db):
    _configure()
    telegram_bot.set_strategy_channel_override("strat1", "channel_A")
    pos = _open_position(strategy_id="strat1")
    storage.log_telegram_message("pos1", "strat1", "Test Strategy", "manual", "text", True, None,
                                  "2026-01-01T00:00:00+00:00")
    closed_position = {**pos, "pnl": 10.0, "pnl_pct": 10.0, "exit_price": 110.0, "exit_reason": "take_profit"}

    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        telegram_bot.send_close_followup(closed_position)
    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs["channel_id_override"] == "channel_A"


def test_omitting_the_override_kwarg_still_uses_the_default_channel(test_db, monkeypatch):
    """Every OTHER existing caller of _raw_send (daily/weekly reports, test
    sends) never passes channel_id_override -- confirms that path is
    completely unaffected by this feature."""
    _configure()
    captured = {}

    class _FakeResponse:
        status_code = 200
        def json(self):
            return {"ok": True}

    def _fake_post(url, json, timeout, proxies):
        captured["chat_id"] = json["chat_id"]
        return _FakeResponse()

    monkeypatch.setattr(telegram_bot.requests, "post", _fake_post)
    telegram_bot._raw_send("hello")  # no override passed
    assert captured["chat_id"] == "default_channel"
