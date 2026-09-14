"""Grand Master Batch, Phase 6 Item 16 -- Group-Selection Mode.

Lets the CEO choose to receive only one strategy_groups classification
(Profitable/Losing/Challenge) on the default channel, or everything.
A per-strategy channel override always bypasses the filter.
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


def _position(**overrides):
    base = {"id": "pos1", "strategy_id": "strat1", "strategy_name": "Test Strategy",
            "symbol": "BTCUSDT", "direction": "long", "entry_price": 100.0,
            "stop_loss": 95.0, "take_profit": 110.0}
    base.update(overrides)
    return base


def test_default_filter_is_all_and_never_blocks():
    ok, reason = telegram_bot.group_filter_check(_position())
    assert ok is True


def test_filter_blocks_a_non_matching_group(test_db):
    telegram_bot.save_settings(channel_group_filter="challenge")
    storage.upsert_paper_strategy_groups_batch({"strat1": "profitable"}, datetime.now(timezone.utc).isoformat())
    ok, reason = telegram_bot.group_filter_check(_position())
    assert ok is False
    assert "challenge" in reason


def test_filter_allows_a_matching_group(test_db):
    telegram_bot.save_settings(channel_group_filter="challenge")
    storage.upsert_paper_strategy_groups_batch({"strat1": "challenge"}, datetime.now(timezone.utc).isoformat())
    ok, reason = telegram_bot.group_filter_check(_position())
    assert ok is True


def test_filter_blocks_an_unclassified_strategy_when_restricted(test_db):
    telegram_bot.save_settings(channel_group_filter="profitable")
    ok, reason = telegram_bot.group_filter_check(_position())
    assert ok is False
    assert "not yet classified" in reason


def test_per_strategy_channel_override_bypasses_the_filter(test_db):
    telegram_bot.save_settings(channel_group_filter="challenge")
    storage.upsert_paper_strategy_groups_batch({"strat1": "losing"}, datetime.now(timezone.utc).isoformat())
    telegram_bot.set_strategy_channel_override("strat1", "-100999")
    ok, reason = telegram_bot.group_filter_check(_position())
    assert ok is True


def test_filtered_signal_is_never_sent(test_db):
    telegram_bot.save_settings(bot_token="dummy", channel_id="123", channel_group_filter="challenge")
    storage.open_paper_position({
        "id": "pos1", "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": int(datetime.now(timezone.utc).timestamp() * 1000),
        "created_at": "2026-01-01T00:00:00+00:00", "strategy_id": "strat1", "strategy_name": "Test Strategy",
    })
    storage.upsert_paper_strategy_groups_batch({"strat1": "profitable"}, datetime.now(timezone.utc).isoformat())

    with patch("requests.post") as mock_post:
        result = telegram_bot.send_signal_for_position("pos1", trigger_type="manual")

    assert result["ok"] is False
    mock_post.assert_not_called()


def test_public_settings_reports_the_filter():
    telegram_bot.save_settings(channel_group_filter="losing")
    assert telegram_bot.public_settings()["channel_group_filter"] == "losing"
