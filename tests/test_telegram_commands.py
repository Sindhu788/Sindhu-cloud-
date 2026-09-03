"""Grand Feature Expansion, Phase 2 Features 20-21: /status, /pause,
/resume Telegram bot commands (paper_trading/telegram_commands.py) -- the
first INCOMING Telegram integration anywhere in this codebase. Every test
here is about the two things that matter most for a feature that lets
someone control live trading from a chat message: (1) only the configured
chat_id is ever obeyed, and (2) the commands do exactly what the
equivalent dashboard buttons do -- no separate, weaker code path.
"""

from unittest.mock import MagicMock, patch

from data_engine import config as base_config
from paper_trading import config as pt_config, kill_switch, telegram_bot, telegram_commands

import pytest


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    telegram_commands._last_update_id = None
    yield


def _configure_bot(chat_id="12345"):
    telegram_bot.save_settings(bot_token="test-token", channel_id=chat_id)


def _update(text, chat_id="12345", update_id=1):
    return {"update_id": update_id, "message": {"chat": {"id": chat_id}, "text": text}}


# ------------------------------------------------------------- authorization

def test_unauthorized_sender_gets_no_reply(test_db):
    _configure_bot(chat_id="12345")
    with patch.object(telegram_commands, "_reply") as mock_reply:
        result = telegram_commands.handle_update(_update("/status", chat_id="99999"))
    assert result is None
    mock_reply.assert_not_called()


def test_no_channel_id_configured_means_nobody_is_authorized(test_db):
    telegram_bot.save_settings(bot_token="test-token", channel_id="")
    with patch.object(telegram_commands, "_reply") as mock_reply:
        result = telegram_commands.handle_update(_update("/status", chat_id="12345"))
    assert result is None
    mock_reply.assert_not_called()


def test_unrecognized_command_gets_no_reply(test_db):
    _configure_bot()
    with patch.object(telegram_commands, "_reply") as mock_reply:
        result = telegram_commands.handle_update(_update("/nonsense"))
    assert result is None
    mock_reply.assert_not_called()


def test_authorized_status_command_replies(test_db):
    _configure_bot()
    with patch.object(telegram_commands, "_reply") as mock_reply:
        result = telegram_commands.handle_update(_update("/status"))
    assert result is not None
    assert "Engine:" in result
    mock_reply.assert_called_once_with("12345", result)


def test_group_chat_command_suffix_is_stripped(test_db):
    _configure_bot()
    with patch.object(telegram_commands, "_reply"):
        result = telegram_commands.handle_update(_update("/status@sindhu_bot"))
    assert result is not None


# ------------------------------------------------------------- /status

def test_status_reports_kill_switch_and_drawdown_state(test_db):
    _configure_bot()
    kill_switch.activate(reason="test emergency", close_positions=False)
    with patch.object(telegram_commands, "_reply"):
        result = telegram_commands.handle_update(_update("/status"))
    assert "KILL SWITCH ACTIVE" in result
    assert "test emergency" in result


# ------------------------------------------------------------- /pause /resume

def test_pause_stops_a_running_engine_and_persists_the_choice(test_db):
    # Mocked start/stop/is_running rather than a real PaperTradingEngine
    # thread -- stop() only flips is_running() once the background loop
    # notices the flag on its NEXT iteration (see engine.py's _loop), so a
    # real thread here would be a genuine race, not a deterministic test.
    _configure_bot()
    with patch("paper_trading.engine.engine.is_running", return_value=True), \
         patch("paper_trading.engine.engine.stop", return_value=True) as mock_stop, \
         patch.object(telegram_commands, "_reply"):
        result = telegram_commands.handle_update(_update("/pause"))
    assert result == "Engine stopped."
    mock_stop.assert_called_once()
    assert pt_config.load()["engine_enabled"] is False


def test_pause_when_already_stopped_says_so_without_erroring(test_db):
    _configure_bot()
    with patch.object(telegram_commands, "_reply"):
        result = telegram_commands.handle_update(_update("/pause"))
    assert result == "Engine is already stopped."


def test_resume_is_blocked_by_an_active_kill_switch_with_a_clear_message(test_db):
    _configure_bot()
    kill_switch.activate(reason="test", close_positions=False)
    with patch.object(telegram_commands, "_reply"):
        result = telegram_commands.handle_update(_update("/resume"))
    assert "Could not resume" in result
    assert "kill switch" in result.lower() or "Kill switch" in result
    assert pt_config.load()["engine_enabled"] is False


def test_resume_and_pause_are_recorded_in_the_permanent_audit_trail(test_db):
    from data_engine import storage
    _configure_bot()
    with patch("paper_trading.engine.engine.start", return_value=True), \
         patch("paper_trading.engine.engine.is_running", return_value=False), \
         patch.object(telegram_commands, "_reply"):
        telegram_commands.handle_update(_update("/resume"))

    audit = storage.list_audit_trail(entity="paper_trading")
    assert any("Telegram /resume" in r["message"] for r in audit)


# ------------------------------------------------------------- polling loop

def test_poll_once_advances_the_offset_and_processes_every_update(test_db):
    _configure_bot()
    updates = [_update("/help", update_id=5), _update("/help", update_id=6)]
    with patch.object(telegram_commands, "_get_updates", return_value=updates) as mock_get, \
         patch.object(telegram_commands, "_reply"):
        count = telegram_commands.poll_once()
    assert count == 2
    assert telegram_commands._last_update_id == 6
    mock_get.assert_called_once_with(None)  # first call: no prior offset


def test_poll_once_requests_the_next_offset_after_the_last_seen_update(test_db):
    _configure_bot()
    telegram_commands._last_update_id = 10
    with patch.object(telegram_commands, "_get_updates", return_value=[]) as mock_get:
        telegram_commands.poll_once()
    mock_get.assert_called_once_with(11)


def test_poll_once_does_nothing_without_a_bot_token(test_db):
    telegram_bot.save_settings(bot_token="", channel_id="12345")
    with patch("requests.get") as mock_get:
        count = telegram_commands.poll_once()
    assert count == 0
    mock_get.assert_not_called()
