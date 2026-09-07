"""URGENT bug fix, 2026-09-06: a telegram_settings row saved to
cloud_settings BEFORE TELEGRAM_BOT_TOKEN/TELEGRAM_CHANNEL_ID existed as
env vars persists bot_token/channel_id as empty strings, which then
permanently shadowed the env-var defaults forever -- confirmed live on
the CEO's cloud deployment (env vars added + redeployed, dashboard still
showed "Bot Set Up: No"). Fix: fall back to the env var only when the
saved value is empty, never overriding a real saved value."""
from unittest.mock import patch

from data_engine import db_backend
from paper_trading import telegram_bot


def test_empty_saved_values_fall_back_to_env_vars(monkeypatch):
    monkeypatch.setattr(db_backend, "IS_POSTGRES", True)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:ABC-from-env")
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "-100999-from-env")
    with patch.object(telegram_bot.storage, "get_cloud_setting", return_value={"bot_token": "", "channel_id": ""}):
        settings = telegram_bot.load_settings()
    assert settings["bot_token"] == "123:ABC-from-env"
    assert settings["channel_id"] == "-100999-from-env"


def test_real_saved_values_are_never_overridden_by_env_vars(monkeypatch):
    monkeypatch.setattr(db_backend, "IS_POSTGRES", True)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "env-token-should-not-win")
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "env-channel-should-not-win")
    with patch.object(telegram_bot.storage, "get_cloud_setting",
                       return_value={"bot_token": "real-saved-token", "channel_id": "real-saved-channel"}):
        settings = telegram_bot.load_settings()
    assert settings["bot_token"] == "real-saved-token"
    assert settings["channel_id"] == "real-saved-channel"


def test_no_saved_row_at_all_still_uses_env_vars(monkeypatch):
    monkeypatch.setattr(db_backend, "IS_POSTGRES", True)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fresh-deploy-token")
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "fresh-deploy-channel")
    with patch.object(telegram_bot.storage, "get_cloud_setting", return_value=None):
        settings = telegram_bot.load_settings()
    assert settings["bot_token"] == "fresh-deploy-token"
    assert settings["channel_id"] == "fresh-deploy-channel"
