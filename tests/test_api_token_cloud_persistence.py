"""sindhu_web/security.py's get_or_create_token() -- Master Task 3, Phase
0.3 (dashboard control buttons not responding on the cloud deploy).

THE BUG: every other piece of state this project persists across a
restart on Render (login credentials/sessions, Paper Trading settings,
Telegram settings) was already moved onto the cloud_settings/Postgres
pattern -- except this one. get_or_create_token() wrote/read a local
api_token.json file unconditionally, which lives on Render's EPHEMERAL
filesystem. A browser tab that had already cached the old token in
localStorage (see app.js's apiToken/ensureToken) would keep sending that
now-stale token on every state-changing request (Start Engine, Stop
Engine, Dry Run toggle, ...) after any restart/redeploy/sleep-wake --
the server correctly rejects it with 401 "missing or invalid
X-Sindhu-Token header", which from the CEO's side looked exactly like
"the buttons don't respond" (GET-based pages keep loading fine, since
safe methods need no token at all).

Same honest limitation as test_cloud_settings_persistence.py: no real
Postgres server is available here -- a real sqlite3 file substitutes for
storage.get_conn() wherever db_backend.IS_POSTGRES is True, and a
"restart" is simulated by rebinding storage.get_conn to a fresh
connection pointed at the same on-disk file.
"""

import sqlite3
from contextlib import contextmanager

import pytest

from data_engine import db_backend
from sindhu_web import security


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

    import data_engine.storage as storage_module
    monkeypatch.setattr(storage_module, "get_conn", _connect(db_path))
    return db_path


def test_token_survives_a_simulated_restart(cloud_mode, monkeypatch):
    """The actual bug, reproduced and fixed: the SAME token must come back
    after a restart, so a browser tab's cached copy stays valid."""
    token = security.get_or_create_token()
    assert token

    import data_engine.storage as storage_module
    monkeypatch.setattr(storage_module, "get_conn", _connect(cloud_mode))
    assert security.get_or_create_token() == token


def test_token_is_not_regenerated_on_every_call(cloud_mode):
    first = security.get_or_create_token()
    second = security.get_or_create_token()
    assert first == second


@pytest.fixture(autouse=True)
def isolated_local_token_file(tmp_path, monkeypatch):
    monkeypatch.setattr(security, "_TOKEN_PATH", str(tmp_path / "api_token.json"))


def test_local_laptop_mode_is_completely_unaffected(monkeypatch, tmp_path):
    """When DATABASE_URL is unset (every local laptop run), the token
    keeps coming from the local file exactly as before."""
    monkeypatch.setattr(db_backend, "IS_POSTGRES", False)

    token = security.get_or_create_token()
    assert security.get_or_create_token() == token

    import os
    assert os.path.exists(security._TOKEN_PATH)
