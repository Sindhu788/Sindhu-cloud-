"""Grand Master Batch, Phase 4 Item 8 -- Backup Alert Channel.

_raw_send's ntfy.sh fallback (paper_trading/push_notifications.py,
previously built but never called by production code) fires only when
Telegram itself is genuinely unreachable (every retry hit a connection-
level exception), never for a real Telegram-side rejection or a
gate-withheld send -- those aren't "Telegram is down".
"""

from unittest.mock import patch

import requests

from data_engine import config as base_config
from paper_trading import push_notifications, telegram_bot


def test_backup_push_fires_after_genuine_connection_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    telegram_bot.save_settings(bot_token="dummy", channel_id="123")
    with patch("requests.post", side_effect=requests.ConnectionError("network unreachable")), \
         patch.object(push_notifications, "send_push") as mock_push, \
         patch.object(telegram_bot.time, "sleep"):
        ok, err = telegram_bot._raw_send("a real signal message")
    assert ok is False
    assert "failed after" in err
    mock_push.assert_called_once()
    title, message = mock_push.call_args[0][0], mock_push.call_args[0][1]
    assert "Telegram" in title
    assert "a real signal message" in message


def test_backup_push_not_fired_on_a_real_telegram_rejection(monkeypatch, tmp_path):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    telegram_bot.save_settings(bot_token="dummy", channel_id="123")
    with patch("requests.post") as mock_post, patch.object(push_notifications, "send_push") as mock_push:
        mock_post.return_value.status_code = 400
        mock_post.return_value.json.return_value = {"ok": False, "description": "chat not found"}
        ok, err = telegram_bot._raw_send("a real signal message")
    assert ok is False
    assert err == "chat not found"
    mock_push.assert_not_called()


def test_backup_push_failure_never_changes_the_real_send_result(monkeypatch, tmp_path):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    telegram_bot.save_settings(bot_token="dummy", channel_id="123")
    with patch("requests.post", side_effect=requests.ConnectionError("network unreachable")), \
         patch.object(push_notifications, "send_push", side_effect=Exception("ntfy also broken")), \
         patch.object(telegram_bot.time, "sleep"):
        ok, err = telegram_bot._raw_send("a real signal message")
    assert ok is False
    assert "failed after" in err
