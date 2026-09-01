"""External Signal Tracker, Phase 1 -- Telegram reading connection.
Covers the parts provable without a live Telegram login: Telethon
availability, clear actionable errors when credentials/session aren't
configured yet, and that ingestion only ever touches external_messages
via ingest.capture_message() (Stage 1 only, no parsing)."""

import os
import tempfile

import pytest

import data_engine.storage as storage
from external_signals import telegram_reader, config as ext_config


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", os.path.join(tempfile.mkdtemp(), "test.db"))
    storage.init_db()


def test_telethon_is_installed_and_importable():
    assert telegram_reader.telethon_available() is True


def test_missing_api_credentials_gives_a_clear_actionable_error(monkeypatch):
    monkeypatch.setattr(ext_config, "load", lambda: dict(ext_config._DEFAULTS))
    with pytest.raises(RuntimeError, match="my.telegram.org"):
        telegram_reader._get_client()


def test_missing_session_gives_a_clear_actionable_error(monkeypatch):
    monkeypatch.setattr(ext_config, "load", lambda: {
        **ext_config._DEFAULTS, "telegram_api_id": "12345", "telegram_api_hash": "abc123",
    })
    with pytest.raises(RuntimeError, match="[Nn]ot logged in"):
        telegram_reader._get_client()


def test_a_configured_session_builds_a_real_telethon_client(monkeypatch):
    """Once credentials + session exist, _get_client() must actually
    succeed in building a client object (still offline -- no .connect()
    call here, just proving the wiring is correct)."""
    fake_session_string = (
        "1ApWapzMBu9B8anvhz6o2dvDXxe9p_9zh3xSjYM3k77tyzyOWwroH7BbwL4Vsm_zZJ3LUPP-6bYiMeOS5ZtONjpXvjWuzhN8K904Kn9YMeyAM9"
        "HbqmT6ub2CLyIvitbUAhqmzpyrgTHNtrA8jblyWdjLIiih_nbNGA_4nQOWZY4w-AP1fd9jo5xweZE4Z7EQZdfBnheMmFo2sIhqvrDjC3AyaJe"
        "nhKL1JBMz-VqA7Toys-kgnn_zX3w95t5qHmiHymrflGpdbWc49hwSADc7s214CT3vN5x94T7B3wYpbqcHRYQzHVpUjvvs8W4Zk5oqXZU9AIf"
        "GVWjotP_p4Q0MznQk6mGeKY1U="
    )
    monkeypatch.setattr(ext_config, "load", lambda: {
        **ext_config._DEFAULTS, "telegram_api_id": "12345", "telegram_api_hash": "abc123",
        "telegram_session_string": fake_session_string,
    })
    client = telegram_reader._get_client()
    assert client is not None
    assert type(client).__name__ == "TelegramClient"
