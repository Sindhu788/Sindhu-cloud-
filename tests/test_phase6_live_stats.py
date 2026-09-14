"""Grand Master Batch, Phase 6 Item 14 -- Pinned, self-updating "live
stats" message. First call sends + pins a new message and remembers its
id; every later call edits that same message in place instead of
sending a new one.
"""

from unittest.mock import MagicMock, patch

import pytest

from data_engine import config as base_config
from paper_trading import telegram_bot


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _ok_response(extra=None):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"ok": True, **(extra or {})}
    return resp


def test_not_configured_reports_a_clear_error():
    result = telegram_bot.update_live_stats_message()
    assert result["ok"] is False


def test_master_switch_off_blocks_the_update(test_db):
    telegram_bot.save_settings(bot_token="dummy", channel_id="123", master_send_enabled=False)
    result = telegram_bot.update_live_stats_message()
    assert result["ok"] is False
    assert "switched off" in result["error"]


def test_first_call_sends_and_pins_a_new_message(test_db):
    telegram_bot.save_settings(bot_token="dummy", channel_id="123")
    with patch("requests.post") as mock_post:
        mock_post.side_effect = [
            _ok_response({"result": {"message_id": 42}}),  # sendMessage
            _ok_response(),  # pinChatMessage
        ]
        result = telegram_bot.update_live_stats_message()

    assert result["ok"] is True
    assert result["created_new"] is True
    assert result["message_id"] == 42
    calls = [c.args[0] for c in mock_post.call_args_list]
    assert calls[0].endswith("/sendMessage")
    assert calls[1].endswith("/pinChatMessage")
    assert telegram_bot.public_settings()["live_stats_message"] == {"chat_id": "123", "message_id": 42}


def test_second_call_edits_the_existing_message_instead_of_sending_new(test_db):
    telegram_bot.save_settings(bot_token="dummy", channel_id="123",
                                live_stats_message={"chat_id": "123", "message_id": 42})
    with patch("requests.post") as mock_post:
        mock_post.return_value = _ok_response()
        result = telegram_bot.update_live_stats_message()

    assert result["ok"] is True
    assert result["created_new"] is False
    assert mock_post.call_count == 1
    assert mock_post.call_args.args[0].endswith("/editMessageText")
    assert mock_post.call_args.kwargs["json"]["message_id"] == 42


def test_edit_failure_falls_back_to_sending_and_pinning_a_fresh_message(test_db):
    telegram_bot.save_settings(bot_token="dummy", channel_id="123",
                                live_stats_message={"chat_id": "123", "message_id": 42})
    with patch("requests.post") as mock_post:
        mock_post.side_effect = [
            _ok_response({"ok": False}),  # editMessageText fails (e.g. message deleted)
            _ok_response({"result": {"message_id": 99}}),  # sendMessage
            _ok_response(),  # pinChatMessage
        ]
        result = telegram_bot.update_live_stats_message()

    assert result["ok"] is True
    assert result["created_new"] is True
    assert result["message_id"] == 99


def test_live_stats_text_includes_real_numbers(test_db):
    telegram_bot.save_settings(bot_token="dummy", channel_id="123")
    text = telegram_bot._live_stats_text()
    assert "Engine:" in text
    assert "Open trades:" in text
    assert "Combined balance:" in text
    assert "Signals sent today:" in text
