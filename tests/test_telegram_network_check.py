"""paper_trading.telegram_bot.check_telegram_reachability(): a real,
credential-independent network test, added so "is Telegram blocked from
here" can be verified against wherever the process is actually running,
rather than assuming an earlier local-machine finding still applies.
"""
import pytest
import requests
from unittest.mock import patch

from data_engine import config as base_config
from paper_trading import telegram_bot


@pytest.fixture(autouse=True)
def isolated_local_config(tmp_path, monkeypatch):
    """Isolates the LOCAL telegram_settings.json from this project's real
    data/config/ directory -- same convention as
    tests/test_telegram_signal_gate.py and test_telegram_master_switch.py.
    Without this, save_settings() (called by these tests) writes straight
    into the real local file."""
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def test_reports_reachable_on_a_real_looking_response(test_db):
    fake_resp = type("R", (), {"status_code": 404})()
    with patch("requests.get", return_value=fake_resp):
        result = telegram_bot.check_telegram_reachability()
    assert result["reachable"] is True
    assert result["http_status"] == 404
    assert "latency_ms" in result


def test_reports_unreachable_on_a_connection_error(test_db):
    with patch("requests.get", side_effect=requests.ConnectionError("boom")):
        result = telegram_bot.check_telegram_reachability()
    assert result["reachable"] is False
    assert "ConnectionError" in result["error"]


def test_never_needs_a_bot_token_or_channel_id(test_db):
    """Unlike send_test_message(), this must work even before either is
    configured -- that's the whole point (diagnosing reachability BEFORE
    a bot exists)."""
    fake_resp = type("R", (), {"status_code": 404})()
    with patch("requests.get", return_value=fake_resp):
        result = telegram_bot.check_telegram_reachability()
    assert result["reachable"] is True
    assert result["bot_token_configured"] is False
    assert result["channel_id_configured"] is False


def test_includes_safe_config_booleans_never_the_raw_token(test_db):
    telegram_bot.save_settings(bot_token="123:abc", channel_id="-100123")
    fake_resp = type("R", (), {"status_code": 404})()
    with patch("requests.get", return_value=fake_resp):
        result = telegram_bot.check_telegram_reachability()
    assert result["bot_token_configured"] is True
    assert result["channel_id_configured"] is True
    assert "123:abc" not in str(result)
