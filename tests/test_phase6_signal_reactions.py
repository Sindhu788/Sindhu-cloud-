"""Grand Master Batch, Phase 6 Item 15 -- Signal Reaction Tracking.

The first callback_query (inline-button tap) handling anywhere in this
codebase -- every real trade signal now gets a 👍/👎 inline keyboard,
and a tap is logged for later review.
"""

from unittest.mock import patch

import pytest

from data_engine import config as base_config
from paper_trading import signal_reactions, telegram_commands


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


# --------------------------------------------------------------- keyboard / parsing

def test_build_reaction_keyboard_shape():
    kb = signal_reactions.build_reaction_keyboard("pos123")
    buttons = kb["inline_keyboard"][0]
    assert buttons[0]["callback_data"] == "react:up:pos123"
    assert buttons[1]["callback_data"] == "react:down:pos123"


def test_parse_reaction_callback_valid():
    assert signal_reactions.parse_reaction_callback("react:up:pos123") == ("up", "pos123")
    assert signal_reactions.parse_reaction_callback("react:down:pos123") == ("down", "pos123")


def test_parse_reaction_callback_rejects_unrelated_data():
    assert signal_reactions.parse_reaction_callback("something:else") is None
    assert signal_reactions.parse_reaction_callback(None) is None
    assert signal_reactions.parse_reaction_callback("react:sideways:pos123") is None


# --------------------------------------------------------------- storage

def test_record_and_list_reactions():
    signal_reactions.record_reaction("pos1", "up", from_user="ceo")
    signal_reactions.record_reaction("pos1", "down", from_user="teammate")
    signal_reactions.record_reaction("pos2", "up", from_user="ceo")

    assert len(signal_reactions.list_reactions()) == 3
    assert len(signal_reactions.list_reactions("pos1")) == 2
    counts = signal_reactions.reaction_counts("pos1")
    assert counts == {"up": 1, "down": 1}


def test_record_rejects_unknown_reaction():
    with pytest.raises(ValueError):
        signal_reactions.record_reaction("pos1", "sideways")


# --------------------------------------------------------------- telegram_commands integration

def _callback_update(data, chat_id=1, callback_id="cb1"):
    return {"callback_query": {"id": callback_id, "data": data, "from": {"username": "ceo", "id": 1},
                                "message": {"chat": {"id": chat_id}}}}


def test_authorized_reaction_tap_is_recorded_and_answered(test_db, monkeypatch):
    from paper_trading import telegram_bot
    telegram_bot.save_settings(bot_token="dummy", channel_id="123")
    monkeypatch.setattr(telegram_commands, "_is_authorized", lambda chat_id: True)
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}
        result = telegram_commands.handle_update(_callback_update("react:up:pos123"))

    assert result == "reaction:up:pos123"
    assert signal_reactions.reaction_counts("pos123") == {"up": 1, "down": 0}
    # answerCallbackQuery was actually called (stops the tapper's spinner).
    urls = [c.args[0] for c in mock_post.call_args_list]
    assert any(u.endswith("/answerCallbackQuery") for u in urls)


def test_unauthorized_reaction_tap_is_never_recorded(test_db, monkeypatch):
    monkeypatch.setattr(telegram_commands, "_is_authorized", lambda chat_id: False)
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}
        result = telegram_commands.handle_update(_callback_update("react:up:pos123"))

    assert result is None
    assert signal_reactions.list_reactions("pos123") == []


def test_unrecognized_callback_data_is_ignored_but_still_answered(test_db, monkeypatch):
    from paper_trading import telegram_bot
    telegram_bot.save_settings(bot_token="dummy", channel_id="123")
    monkeypatch.setattr(telegram_commands, "_is_authorized", lambda chat_id: True)
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}
        result = telegram_commands.handle_update(_callback_update("some_future_button:xyz"))

    assert result is None
    urls = [c.args[0] for c in mock_post.call_args_list]
    assert any(u.endswith("/answerCallbackQuery") for u in urls)


# --------------------------------------------------------------- signal send wiring

def test_real_signal_includes_the_reaction_keyboard(test_db, monkeypatch):
    from datetime import datetime, timezone
    from data_engine import storage
    from paper_trading import telegram_bot

    monkeypatch.setattr(telegram_bot, "_fetch_live_price", lambda *a, **k: None)
    telegram_bot.save_settings(bot_token="dummy", channel_id="123")
    storage.open_paper_position({
        "id": "pos1", "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": int(datetime.now(timezone.utc).timestamp() * 1000),
        "created_at": "2026-01-01T00:00:00+00:00", "strategy_id": "strat1", "strategy_name": "Test Strategy",
    })
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}
        telegram_bot.send_signal_for_position("pos1", trigger_type="manual")

    sent_markup = mock_post.call_args_list[0].kwargs["json"]["reply_markup"]
    assert sent_markup["inline_keyboard"][0][0]["callback_data"] == "react:up:pos1"
