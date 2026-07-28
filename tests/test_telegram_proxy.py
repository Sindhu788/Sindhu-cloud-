"""Tests for Telegram proxy support (paper_trading/telegram_bot.py) --
verifies the configured proxy is correctly read and applied to outbound
requests, without needing a real network/proxy/Telegram connection.
"""

from unittest.mock import patch, MagicMock

import pytest

from data_engine import config as base_config
from paper_trading import telegram_bot


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """telegram_bot reads/writes through data_engine.config's JSON-file
    store -- without this, these tests would touch the real
    data/config/telegram_settings.json on disk."""
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def test_no_proxy_configured_by_default():
    settings = telegram_bot.load_settings()
    assert settings["proxy_enabled"] is False
    assert settings["proxy_url"] == ""
    assert telegram_bot._build_proxies(settings) is None


def test_proxy_disabled_even_with_url_set_returns_none():
    telegram_bot.save_settings(proxy_enabled=False, proxy_url="socks5://user:pass@host:1080")
    settings = telegram_bot.load_settings()
    assert telegram_bot._build_proxies(settings) is None


def test_proxy_enabled_builds_correct_dict():
    telegram_bot.save_settings(proxy_enabled=True, proxy_url="socks5://user:pass@host:1080")
    settings = telegram_bot.load_settings()
    proxies = telegram_bot._build_proxies(settings)
    assert proxies == {"http": "socks5://user:pass@host:1080", "https": "socks5://user:pass@host:1080"}


def test_proxy_enabled_but_empty_url_returns_none():
    telegram_bot.save_settings(proxy_enabled=True, proxy_url="")
    settings = telegram_bot.load_settings()
    assert telegram_bot._build_proxies(settings) is None


def test_public_settings_never_exposes_raw_proxy_url():
    telegram_bot.save_settings(proxy_enabled=True, proxy_url="socks5://secretuser:secretpass@host:1080")
    pub = telegram_bot.public_settings()
    assert pub["proxy_enabled"] is True
    assert pub["proxy_configured"] is True
    assert "secretuser" not in str(pub)
    assert "secretpass" not in str(pub)
    assert "proxy_url" not in pub


def test_raw_send_passes_configured_proxy_to_requests():
    """The actual code path: with a proxy configured, _raw_send must pass
    it through to requests.post -- mocked here so this test needs no
    real network access."""
    telegram_bot.save_settings(
        bot_token="dummy-token", channel_id="12345",
        proxy_enabled=True, proxy_url="http://user:pass@myproxy:8080",
    )
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {"ok": True}

    with patch("paper_trading.telegram_bot.requests.post", return_value=fake_response) as mock_post:
        ok, err = telegram_bot._raw_send("hello")

    assert ok is True
    assert err is None
    _, kwargs = mock_post.call_args
    assert kwargs["proxies"] == {"http": "http://user:pass@myproxy:8080", "https": "http://user:pass@myproxy:8080"}


def test_raw_send_passes_none_when_proxy_disabled():
    telegram_bot.save_settings(bot_token="dummy-token", channel_id="12345", proxy_enabled=False)
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {"ok": True}

    with patch("paper_trading.telegram_bot.requests.post", return_value=fake_response) as mock_post:
        telegram_bot._raw_send("hello")

    _, kwargs = mock_post.call_args
    assert kwargs["proxies"] is None


def test_test_proxy_connectivity_reports_not_configured():
    result = telegram_bot.test_proxy_connectivity()
    assert result["ok"] is False
    assert "No proxy is configured" in result["error"]


def test_test_proxy_connectivity_uses_configured_proxy():
    telegram_bot.save_settings(proxy_enabled=True, proxy_url="socks5://user:pass@host:1080")
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {"ip": "1.2.3.4"}

    with patch("paper_trading.telegram_bot.requests.get", return_value=fake_response) as mock_get:
        result = telegram_bot.test_proxy_connectivity()

    assert result["ok"] is True
    assert result["exit_ip"] == "1.2.3.4"
    _, kwargs = mock_get.call_args
    assert kwargs["proxies"] == {"http": "socks5://user:pass@host:1080", "https": "socks5://user:pass@host:1080"}
