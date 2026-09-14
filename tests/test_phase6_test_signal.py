"""Grand Master Batch, Phase 6 Item 18 -- Test Signal command.

Distinct from send_test_message (a bare connectivity check) -- sends a
clearly-labeled fake signal through the exact real message format, for
visual/format checking only. Never opens a position or touches the
trade audit trail.
"""

from unittest.mock import patch

import pytest

from data_engine import config as base_config, storage
from paper_trading import telegram_bot, telegram_commands


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def test_send_test_signal_uses_the_real_5_field_format(test_db):
    telegram_bot.save_settings(bot_token="dummy", channel_id="123")
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}
        result = telegram_bot.send_test_signal()

    assert result["ok"] is True
    sent_text = mock_post.call_args.kwargs["json"]["text"]
    assert "TEST SIGNAL" in sent_text
    assert "TESTCOIN" in sent_text
    assert "Entry:" in sent_text
    assert "Stop-Loss:" in sent_text
    assert "Take-Profit:" in sent_text
    assert "Duration:" in sent_text


def test_send_test_signal_never_opens_a_real_position(test_db):
    telegram_bot.save_settings(bot_token="dummy", channel_id="123")
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}
        telegram_bot.send_test_signal()
    assert storage.get_open_paper_positions() == []
    assert storage.list_telegram_messages() == []  # never logged to the real message log either


def test_send_test_signal_reports_failure_honestly(test_db):
    # No bot_token/channel_id configured -- must fail, never pretend success.
    result = telegram_bot.send_test_signal()
    assert result["ok"] is False


def test_telegram_command_sends_a_real_test_signal(test_db, monkeypatch):
    telegram_bot.save_settings(bot_token="dummy", channel_id="123")
    monkeypatch.setattr(telegram_commands, "_is_authorized", lambda chat_id: True)
    monkeypatch.setattr(telegram_commands, "_reply", lambda chat_id, text: None)
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}
        reply = telegram_commands.handle_update({"message": {"chat": {"id": 1}, "text": "/test"}})
    assert "sent" in reply.lower()
    # The real signal-formatted send happened (not just the command's own reply).
    sent_texts = [c.kwargs["json"]["text"] for c in mock_post.call_args_list]
    assert any("TEST SIGNAL" in t for t in sent_texts)
