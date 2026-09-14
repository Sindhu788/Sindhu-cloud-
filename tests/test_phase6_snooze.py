"""Grand Master Batch, Phase 6 Item 12 -- Snooze This Strategy's Signals.

Withholds ONE strategy's Telegram signals entirely (not sent, unlike
Quiet Mode which only mutes the phone alert) until it expires, without
touching any other strategy.
"""

from datetime import datetime, timedelta, timezone
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


def _position(**overrides):
    base = {
        "id": "pos1", "strategy_id": "strat1", "strategy_name": "Test Strategy",
        "symbol": "BTCUSDT", "direction": "long", "entry_price": 100.0,
        "stop_loss": 95.0, "take_profit": 110.0,
    }
    base.update(overrides)
    return base


def test_starts_unsnoozed():
    assert telegram_bot.is_strategy_snoozed("strat1") is False


def test_snooze_activates_it():
    telegram_bot.snooze_strategy("strat1", hours=24)
    assert telegram_bot.is_strategy_snoozed("strat1") is True


def test_snooze_expires():
    telegram_bot.snooze_strategy("strat1", hours=1)
    future = datetime.now(timezone.utc) + timedelta(hours=2)
    assert telegram_bot.is_strategy_snoozed("strat1", now=future) is False


def test_unsnooze_turns_it_off_early():
    telegram_bot.snooze_strategy("strat1", hours=24)
    telegram_bot.unsnooze_strategy("strat1")
    assert telegram_bot.is_strategy_snoozed("strat1") is False


def test_snoozing_one_strategy_never_affects_another():
    telegram_bot.snooze_strategy("strat1", hours=24)
    assert telegram_bot.is_strategy_snoozed("strat2") is False


def test_snooze_rejects_non_positive_hours():
    with pytest.raises(ValueError):
        telegram_bot.snooze_strategy("strat1", hours=0)


def test_snoozed_strategy_signal_is_withheld_entirely(test_db):
    telegram_bot.save_settings(bot_token="dummy", channel_id="123")
    storage.open_paper_position({
        "id": "pos1", "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": int(datetime.now(timezone.utc).timestamp() * 1000),
        "created_at": "2026-01-01T00:00:00+00:00", "strategy_id": "strat1", "strategy_name": "Test Strategy",
    })
    telegram_bot.snooze_strategy("strat1", hours=24)

    with patch("requests.post") as mock_post:
        result = telegram_bot.send_signal_for_position("pos1", trigger_type="manual")

    assert result["ok"] is False
    assert "snoozed" in result["error"]
    mock_post.assert_not_called()


def test_public_settings_reports_snoozed_strategies():
    telegram_bot.snooze_strategy("strat1", hours=24)
    s = telegram_bot.public_settings()
    assert "strat1" in s["snoozed_strategies"]
