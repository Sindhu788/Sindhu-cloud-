"""paper_trading/config.py + paper_trading/telegram_bot.py -- Postgres-backed
settings persistence for the cloud runner.

THE BUG (same shape as Part 1's login-credentials fix, tests/
test_auth_cloud_persistence.py): both files stored their settings via
data_engine.config.load_or_seed()/save_config() -- a local JSON file.
Render's free tier filesystem is EPHEMERAL, so a CEO turning "Dry Run
Mode" off (or any other dashboard toggle -- engine on/off, Telegram
auto-send, confidence thresholds) would silently see it revert to the
conservative default on the next restart/redeploy/sleep-wake, with
nothing in the UI to explain why. This directly undermines "the engine
should run continuously" -- resume_engine_on_startup() (paper_trading/
engine.py) only restores what pt_config.load() reports, so a lost
"engine_enabled: True" means the engine silently stays off after a
restart even though the CEO explicitly started it.

Same honest limitation as test_auth_cloud_persistence.py: no real
Postgres server is available in this environment. These tests substitute
a real sqlite3 file connection wherever storage.get_conn() is called
under db_backend.IS_POSTGRES -- proving genuine INSERT/UPDATE/SELECT
round-trips against the exact SQL text these modules issue, not just
mocked call arguments. A "restart" is simulated honestly: rebinding
storage.get_conn to a brand new connection function pointed at the SAME
on-disk file, so nothing from a held-open Python connection/object can
leak through -- only what was actually committed to disk comes back.
"""

import sqlite3
from contextlib import contextmanager

import pytest

from data_engine import config as base_config
from data_engine import db_backend
from paper_trading import config as pt_config
from paper_trading import telegram_bot


def _connect(db_path):
    @contextmanager
    def _get_conn():
        c = sqlite3.connect(str(db_path))
        try:
            yield c
            c.commit()
        finally:
            c.close()
    return _get_conn


@pytest.fixture
def cloud_mode(monkeypatch, tmp_path):
    monkeypatch.setattr(db_backend, "IS_POSTGRES", True)
    db_path = tmp_path / "fake_postgres.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""CREATE TABLE cloud_settings (
        key TEXT PRIMARY KEY, value_json TEXT NOT NULL, updated_at TEXT NOT NULL)""")
    conn.commit()
    conn.close()
    monkeypatch.setattr(pt_config.storage, "get_conn", _connect(db_path))
    monkeypatch.setattr(telegram_bot.storage, "get_conn", _connect(db_path))
    return db_path


def test_paper_trading_settings_start_at_defaults(cloud_mode):
    settings = pt_config.load()
    assert settings["dry_run"] is True
    assert settings["engine_enabled"] is False
    assert settings["max_open_trades"] == 5


def test_dry_run_toggle_survives_a_simulated_restart(cloud_mode, monkeypatch):
    """The actual bug, reproduced and fixed: a CEO turning Dry Run Mode off
    (the exact action Part 3 of this task asks to confirm) must still read
    back as off after a restart, not silently revert to the safe default."""
    pt_config.update(dry_run=False)
    assert pt_config.load()["dry_run"] is False

    monkeypatch.setattr(pt_config.storage, "get_conn", _connect(cloud_mode))
    assert pt_config.load()["dry_run"] is False


def test_engine_enabled_flag_survives_a_simulated_restart(cloud_mode, monkeypatch):
    """resume_engine_on_startup() (paper_trading/engine.py) depends on this
    exact flag to bring the engine back up after a restart -- if this were
    still lost, "24/7 operation" would silently mean "until the next
    restart" on any host without this fix."""
    pt_config.update(engine_enabled=True)

    monkeypatch.setattr(pt_config.storage, "get_conn", _connect(cloud_mode))
    assert pt_config.load()["engine_enabled"] is True


def test_partial_update_does_not_clobber_other_saved_settings(cloud_mode):
    pt_config.update(dry_run=False)
    pt_config.update(max_open_trades=3)
    settings = pt_config.load()
    assert settings["dry_run"] is False
    assert settings["max_open_trades"] == 3


def test_telegram_settings_survive_a_simulated_restart(cloud_mode, monkeypatch):
    telegram_bot.save_settings(auto_send_enabled=True, auto_send_min_confluence_count=4)

    monkeypatch.setattr(telegram_bot.storage, "get_conn", _connect(cloud_mode))
    settings = telegram_bot.load_settings()
    assert settings["auto_send_enabled"] is True
    assert settings["auto_send_min_confluence_count"] == 4
    # Untouched defaults must still come through the merge unchanged.
    assert settings["signal_freshness_minutes"] == 15


@pytest.fixture(autouse=True)
def isolated_local_config(tmp_path, monkeypatch):
    """Same isolation pattern as test_auth_cloud_persistence.py /
    test_telegram_master_switch.py -- keeps the local-JSON-file branch
    below from ever touching the real project's data/config/ directory."""
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))


def test_local_laptop_mode_is_completely_unaffected(monkeypatch):
    """When DATABASE_URL is unset (every local laptop run), both modules
    must keep using their local JSON files exactly as before."""
    monkeypatch.setattr(db_backend, "IS_POSTGRES", False)

    pt_config.update(dry_run=False)
    assert pt_config.load()["dry_run"] is False
    telegram_bot.save_settings(auto_send_enabled=True)
    assert telegram_bot.load_settings()["auto_send_enabled"] is True

    import os
    assert os.path.exists(os.path.join(base_config.CONFIG_DIR, "paper_trading_settings.json"))
    assert os.path.exists(os.path.join(base_config.CONFIG_DIR, "telegram_settings.json"))
