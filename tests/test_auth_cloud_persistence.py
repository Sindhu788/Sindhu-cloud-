"""sindhu_web/auth.py -- Postgres-backed credential/session persistence
for the cloud runner.

THE BUG: on Render's free tier, credentials were stored via
data_engine.config.save_config() -- a local JSON file. Render's filesystem
there is EPHEMERAL: it is wiped on every restart/redeploy/sleep-wake cycle,
so a CEO who set up a username/password would see "first-time setup" again
the next time the host recycled, as if the account had never been created.

No real Postgres server is available in this environment (same stated
limitation as tests/test_db_backend.py). These tests substitute a real
sqlite3 file connection wherever auth.py calls storage.get_conn() under
db_backend.IS_POSTGRES -- sqlite's placeholder syntax and UPSERT
(`ON CONFLICT ... DO UPDATE ... EXCLUDED`) are close enough to Postgres's
to run the *exact* SQL text auth.py issues, proving genuine INSERT/UPDATE/
SELECT round-trips rather than just mocked call arguments. Re-opening a
brand new connection to the SAME on-disk file between "phases" -- never one
held-open connection, never :memory: -- is the honest proxy for "an
external Postgres database, unlike Render's ephemeral local disk, survives
an app restart": the data has to come back from the file itself, never
from anything cached in a Python object.
"""

import sqlite3
from contextlib import contextmanager

import pytest

from data_engine import config as base_config
from data_engine import db_backend
from sindhu_web import auth


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
    """Forces auth.py onto the Postgres branch, backed by a real (if
    stand-in) SQL engine at a real on-disk path -- not :memory:, so a fresh
    connection genuinely has to read persisted rows back off disk, the same
    way a fresh connection to a real Postgres server would."""
    monkeypatch.setattr(db_backend, "IS_POSTGRES", True)
    db_path = tmp_path / "fake_postgres.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""CREATE TABLE auth_credentials (
        id INTEGER PRIMARY KEY, username TEXT NOT NULL, salt TEXT NOT NULL,
        password_hash TEXT NOT NULL, updated_at TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE auth_sessions (
        token TEXT PRIMARY KEY, created_at TEXT NOT NULL, expires_at TEXT NOT NULL)""")
    conn.commit()
    conn.close()
    monkeypatch.setattr(auth.storage, "get_conn", _connect(db_path))
    return db_path


def test_no_credentials_before_setup(cloud_mode):
    assert auth.has_credentials() is False


def test_set_credentials_then_verify_in_the_same_process(cloud_mode):
    auth.set_credentials("ceo", "Secret123!")
    assert auth.has_credentials() is True
    assert auth.verify_password("ceo", "Secret123!") is True
    assert auth.verify_password("ceo", "wrong-password") is False
    assert auth.verify_password("someone-else", "Secret123!") is False


def test_credentials_survive_a_simulated_restart(cloud_mode, monkeypatch):
    """The actual bug, reproduced and fixed: credentials set BEFORE a
    restart must still verify AFTER one. "Restart" is simulated by
    rebinding storage.get_conn to a brand new connection function -- so
    nothing from phase one's Python objects can leak through, only what
    was actually committed to the on-disk file is visible."""
    auth.set_credentials("ceo", "Secret123!")

    monkeypatch.setattr(auth.storage, "get_conn", _connect(cloud_mode))

    assert auth.has_credentials() is True
    assert auth.verify_password("ceo", "Secret123!") is True
    assert auth.verify_password("ceo", "wrong-password") is False


def test_changing_password_persists_the_new_hash(cloud_mode, monkeypatch):
    auth.set_credentials("ceo", "OldPass1")
    assert auth.change_password("OldPass1", "NewPass2") is True

    monkeypatch.setattr(auth.storage, "get_conn", _connect(cloud_mode))
    assert auth.verify_password("ceo", "NewPass2") is True
    assert auth.verify_password("ceo", "OldPass1") is False


def test_change_password_rejects_wrong_current_password(cloud_mode):
    auth.set_credentials("ceo", "OldPass1")
    assert auth.change_password("totally-wrong", "NewPass2") is False
    assert auth.verify_password("ceo", "OldPass1") is True


def test_sessions_survive_a_simulated_restart(cloud_mode, monkeypatch):
    token = auth.create_session()
    assert auth.is_valid_session(token) is True

    monkeypatch.setattr(auth.storage, "get_conn", _connect(cloud_mode))
    assert auth.is_valid_session(token) is True


def test_expired_session_is_rejected(cloud_mode):
    token = "expired-token"
    with auth.storage.get_conn() as conn:
        conn.execute(
            "INSERT INTO auth_sessions (token, created_at, expires_at) VALUES (?, ?, ?)",
            (token, "2020-01-01T00:00:00+00:00", "2020-01-02T00:00:00+00:00"),
        )
    assert auth.is_valid_session(token) is False


def test_invalidate_session_removes_it(cloud_mode):
    token = auth.create_session()
    assert auth.is_valid_session(token) is True
    auth.invalidate_session(token)
    assert auth.is_valid_session(token) is False


@pytest.fixture(autouse=True)
def isolated_local_config(tmp_path, monkeypatch):
    """Same isolation pattern already used throughout tests/ (see
    test_telegram_master_switch.py) so the local-JSON-file branch below
    never touches the real project's data/config/ directory."""
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))


def test_local_laptop_mode_is_completely_unaffected(monkeypatch):
    """When DATABASE_URL is unset (every local laptop run), auth.py must
    keep using the local JSON file exactly as before -- this fix must
    change cloud behavior only, never local behavior."""
    monkeypatch.setattr(db_backend, "IS_POSTGRES", False)

    assert auth.has_credentials() is False
    auth.set_credentials("ceo", "LocalPass1")
    assert auth.has_credentials() is True
    assert auth.verify_password("ceo", "LocalPass1") is True

    import os
    assert os.path.exists(os.path.join(base_config.CONFIG_DIR, "auth_credentials.json"))
