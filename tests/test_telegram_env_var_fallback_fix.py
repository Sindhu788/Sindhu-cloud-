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


# --------------------------------------------------------------- LOCAL branch
# 2026-09-16 audit: the fix above was only ever applied to the Postgres
# branch. The local (laptop) branch had the identical bug -- load_or_seed()
# does merged.update(file_contents), so a telegram_settings.json holding
# "bot_token": "" shadowed the _DEFAULTS entry that reads the env var.
# Found live on the CEO's laptop: the real file holds "" for both keys.

def _local(monkeypatch, tmp_path, file_contents):
    """Local branch (IS_POSTGRES False) reading a real settings file from an
    ISOLATED CONFIG_DIR -- never the real data/config/."""
    import json

    from data_engine import config as base_config

    monkeypatch.setattr(db_backend, "IS_POSTGRES", False)
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    (tmp_path / "telegram_settings.json").write_text(json.dumps(file_contents), encoding="utf-8")
    return telegram_bot.load_settings()


def test_local_empty_saved_values_fall_back_to_env_vars(test_db, monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:ABC-local-env")
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "-100777-local-env")
    settings = _local(monkeypatch, tmp_path, {"bot_token": "", "channel_id": ""})
    assert settings["bot_token"] == "123:ABC-local-env"
    assert settings["channel_id"] == "-100777-local-env"


def test_local_real_saved_values_are_never_overridden(test_db, monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "env-token-should-not-win")
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "env-channel-should-not-win")
    settings = _local(monkeypatch, tmp_path,
                      {"bot_token": "real-local-token", "channel_id": "real-local-channel"})
    assert settings["bot_token"] == "real-local-token"
    assert settings["channel_id"] == "real-local-channel"


def test_local_no_env_vars_leaves_empty_as_empty(test_db, monkeypatch, tmp_path):
    """Without env vars set, an empty saved value stays empty -- the fix must
    not invent a value or crash."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHANNEL_ID", raising=False)
    settings = _local(monkeypatch, tmp_path, {"bot_token": "", "channel_id": ""})
    assert settings["bot_token"] == ""
    assert settings["channel_id"] == ""
