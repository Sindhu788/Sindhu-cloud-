"""Grand Master Batch, Phase 6 Item 20 -- Multi-Recipient Support.

Every additional channel gets a real COPY of a signal, fanned out on
top of the primary destination (default channel or per-strategy
override) -- distinct from channel routing (which REPLACES the
destination, one channel at a time).
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


def test_starts_with_no_additional_channels():
    assert telegram_bot.public_settings()["additional_channel_ids"] == []


def test_add_and_remove_additional_channel():
    telegram_bot.add_additional_channel("-100111")
    assert telegram_bot.public_settings()["additional_channel_ids"] == ["-100111"]
    telegram_bot.remove_additional_channel("-100111")
    assert telegram_bot.public_settings()["additional_channel_ids"] == []


def test_adding_the_same_channel_twice_is_a_no_op():
    telegram_bot.add_additional_channel("-100111")
    telegram_bot.add_additional_channel("-100111")
    assert telegram_bot.public_settings()["additional_channel_ids"] == ["-100111"]


def test_add_rejects_empty_channel_id():
    with pytest.raises(ValueError):
        telegram_bot.add_additional_channel("")


def test_signal_is_fanned_out_to_every_additional_channel(test_db):
    telegram_bot.save_settings(bot_token="dummy", channel_id="123")
    telegram_bot.add_additional_channel("-100111")
    telegram_bot.add_additional_channel("-100222")
    storage.open_paper_position({
        "id": "pos1", "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": int(datetime.now(timezone.utc).timestamp() * 1000),
        "created_at": "2026-01-01T00:00:00+00:00", "strategy_id": "strat1", "strategy_name": "Test Strategy",
    })

    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}
        result = telegram_bot.send_signal_for_position("pos1", trigger_type="manual")

    assert result["ok"] is True
    sent_chat_ids = [c.kwargs["json"]["chat_id"] for c in mock_post.call_args_list]
    assert sent_chat_ids == ["123", "-100111", "-100222"]
    # All three got the exact same message text.
    sent_texts = {c.kwargs["json"]["text"] for c in mock_post.call_args_list}
    assert len(sent_texts) == 1


def test_a_failing_additional_channel_never_changes_the_primary_result(test_db):
    telegram_bot.save_settings(bot_token="dummy", channel_id="123")
    telegram_bot.add_additional_channel("-100111")
    storage.open_paper_position({
        "id": "pos1", "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": int(datetime.now(timezone.utc).timestamp() * 1000),
        "created_at": "2026-01-01T00:00:00+00:00", "strategy_id": "strat1", "strategy_name": "Test Strategy",
    })

    def fake_post(url, json=None, timeout=None, proxies=None):
        from unittest.mock import MagicMock
        resp = MagicMock()
        if json["chat_id"] == "-100111":
            raise Exception("secondary channel exploded")
        resp.status_code = 200
        resp.json.return_value = {"ok": True}
        return resp

    with patch("requests.post", side_effect=fake_post):
        result = telegram_bot.send_signal_for_position("pos1", trigger_type="manual")

    assert result["ok"] is True  # primary send unaffected by the secondary's failure
