"""Master Task Expansion, Part 4: Simple Paper-Trading Status Ping.
See paper_trading/status_ping.py's module docstring for the full design.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from data_engine import config as base_config
from paper_trading import status_ping


@pytest.fixture(autouse=True)
def isolated_local_config(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(config_dir))
    yield


def _fake_engine_status(running=True, balance=10500.25, open_trades=2, last_tick_at=None):
    return {"running": running, "balance": balance, "open_trades": open_trades, "last_tick_at": last_tick_at}


# ------------------------------------------------------------- build_status_message

def test_message_reports_normal_running_state():
    now = datetime.now(timezone.utc).isoformat()
    with patch("paper_trading.engine.engine") as fake_engine:
        fake_engine.status.return_value = _fake_engine_status(running=True, last_tick_at=now)
        text, is_warning = status_ping.build_status_message()
    assert is_warning is False
    assert "running normally" in text
    assert "10500.25" in text
    assert "Open trades: 2" in text


def test_message_flags_engine_off_as_a_warning():
    with patch("paper_trading.engine.engine") as fake_engine:
        fake_engine.status.return_value = _fake_engine_status(running=False, last_tick_at=None)
        text, is_warning = status_ping.build_status_message()
    assert is_warning is True
    assert "currently OFF" in text


def test_message_flags_a_stuck_engine_as_a_warning():
    old_tick = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    with patch("paper_trading.engine.engine") as fake_engine:
        fake_engine.status.return_value = _fake_engine_status(running=True, last_tick_at=old_tick)
        text, is_warning = status_ping.build_status_message()
    assert is_warning is True
    assert "STUCK" in text


def test_message_does_not_flag_a_recent_tick_as_stuck():
    recent_tick = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    with patch("paper_trading.engine.engine") as fake_engine:
        fake_engine.status.return_value = _fake_engine_status(running=True, last_tick_at=recent_tick)
        text, is_warning = status_ping.build_status_message()
    assert is_warning is False
    assert "running normally" in text


# ------------------------------------------------------------- send_status_ping_now

def test_send_is_skipped_honestly_when_no_personal_chat_id_configured():
    with patch("paper_trading.telegram_bot.load_settings", return_value={"personal_chat_id": ""}):
        result = status_ping.send_status_ping_now()
    assert result == {"ok": False, "skipped": True, "reason": "no personal_chat_id configured yet"}


def test_send_actually_calls_send_private_message_and_records_state():
    with patch("paper_trading.telegram_bot.load_settings", return_value={"personal_chat_id": "12345"}), \
         patch("paper_trading.telegram_bot.send_private_message", return_value={"ok": True, "error": None}) as mock_send, \
         patch("paper_trading.engine.engine") as fake_engine:
        fake_engine.status.return_value = _fake_engine_status(running=True, last_tick_at=datetime.now(timezone.utc).isoformat())
        result = status_ping.send_status_ping_now()
    assert result["ok"] is True
    assert result["skipped"] is False
    mock_send.assert_called_once()
    sent_text = mock_send.call_args[0][0]
    assert "SINDHU Paper Trading" in sent_text
    assert status_ping.get_state()["last_sent_at"] is not None


def test_a_failed_send_does_not_silently_look_like_success():
    with patch("paper_trading.telegram_bot.load_settings", return_value={"personal_chat_id": "12345"}), \
         patch("paper_trading.telegram_bot.send_private_message", return_value={"ok": False, "error": "Telegram API error"}), \
         patch("paper_trading.engine.engine") as fake_engine:
        fake_engine.status.return_value = _fake_engine_status()
        result = status_ping.send_status_ping_now()
    assert result["ok"] is False
    assert result["error"] == "Telegram API error"


# ------------------------------------------------------------- scheduling gate

def test_should_send_now_true_when_never_sent_before():
    assert status_ping._should_send_now() is True


def test_should_send_now_false_right_after_sending():
    status_ping._save_state(last_sent_at=datetime.now(timezone.utc).isoformat())
    assert status_ping._should_send_now() is False


def test_should_send_now_true_once_the_interval_has_elapsed():
    long_ago = (datetime.now(timezone.utc) - timedelta(seconds=status_ping.PING_INTERVAL_SECONDS + 60)).isoformat()
    status_ping._save_state(last_sent_at=long_ago)
    assert status_ping._should_send_now() is True
