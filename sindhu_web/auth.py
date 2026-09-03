"""Login gate (Master Task 2, Part 5) -- groundwork for eventual cloud
deployment, built now while the app is still LAN-only. A single-account
username/password login, stored hashed (PBKDF2-HMAC-SHA256, per-account
random salt -- never plaintext), gating every dashboard/API request via
security.py's middleware. This sits ON TOP OF the existing LAN-only +
state-changing-request token guard, not instead of it.

Sessions are a random token stored server-side with an expiry -- simple and
sufficient for a single-user personal tool; no external auth dependency
needed.

STORAGE BACKEND: on the local laptop (DATABASE_URL unset) this is a small
JSON file under data/config/, same pattern security.py already uses for its
own token -- unchanged, since the local disk is permanent there. On the
cloud runner (DATABASE_URL set, see data_engine/db_backend.py), the JSON
file approach is actively wrong: Render's free-tier filesystem is
EPHEMERAL and gets wiped on every restart/redeploy/sleep-wake cycle, so
credentials "saved" there vanished the next time the host recycled,
re-triggering the first-time-setup screen even though the CEO had already
created an account. Both functions below branch on db_backend.IS_POSTGRES
and, when true, read/write the auth_credentials/auth_sessions tables in the
same curated Postgres database paper_positions etc. already use -- which
genuinely survives restarts, being a separate managed service, not local
disk.
"""

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

from data_engine import config as base_config
from data_engine import db_backend, storage

_CRED_FILE = "auth_credentials.json"
_SESSIONS_FILE = "auth_sessions.json"
_PBKDF2_ITERATIONS = 200_000
SESSION_LIFETIME_DAYS = 30

SESSION_COOKIE = "sindhu_session"


def _now():
    return datetime.now(timezone.utc)


def _current_username():
    if db_backend.IS_POSTGRES:
        with storage.get_conn() as conn:
            row = conn.execute("SELECT username FROM auth_credentials WHERE id = 1").fetchone()
        return row[0] if row else ""
    creds = base_config.load_or_seed(_CRED_FILE, {})
    return creds.get("username", "")


def has_credentials():
    if db_backend.IS_POSTGRES:
        with storage.get_conn() as conn:
            row = conn.execute(
                "SELECT username, password_hash FROM auth_credentials WHERE id = 1"
            ).fetchone()
        return bool(row and row[0] and row[1])
    creds = base_config.load_or_seed(_CRED_FILE, {})
    return bool(creds.get("username") and creds.get("password_hash"))


def _hash_password(password, salt_hex=None):
    salt = bytes.fromhex(salt_hex) if salt_hex else os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return salt.hex(), digest.hex()


def set_credentials(username, password):
    salt_hex, hash_hex = _hash_password(password)
    updated_at = _now().isoformat()
    if db_backend.IS_POSTGRES:
        with storage.get_conn() as conn:
            conn.execute(
                """INSERT INTO auth_credentials (id, username, salt, password_hash, updated_at)
                   VALUES (1, ?, ?, ?, ?)
                   ON CONFLICT (id) DO UPDATE SET
                       username = EXCLUDED.username,
                       salt = EXCLUDED.salt,
                       password_hash = EXCLUDED.password_hash,
                       updated_at = EXCLUDED.updated_at""",
                (username, salt_hex, hash_hex, updated_at),
            )
        return
    base_config.save_config(_CRED_FILE, {
        "username": username, "salt": salt_hex, "password_hash": hash_hex,
        "updated_at": updated_at,
    })


def verify_password(username, password):
    if db_backend.IS_POSTGRES:
        with storage.get_conn() as conn:
            row = conn.execute(
                "SELECT username, salt, password_hash FROM auth_credentials WHERE id = 1"
            ).fetchone()
        if not row or not row[0] or not row[2]:
            return False
        db_username, salt, password_hash = row
        if username != db_username:
            return False
        _, hash_hex = _hash_password(password, salt)
        return secrets.compare_digest(hash_hex, password_hash)
    creds = base_config.load_or_seed(_CRED_FILE, {})
    if not creds.get("username") or not creds.get("password_hash"):
        return False
    if username != creds["username"]:
        return False
    _, hash_hex = _hash_password(password, creds["salt"])
    return secrets.compare_digest(hash_hex, creds["password_hash"])


def change_password(current_password, new_password):
    username = _current_username()
    if not verify_password(username, current_password):
        return False
    set_credentials(username, new_password)
    return True


def _load_sessions():
    return base_config.load_or_seed(_SESSIONS_FILE, {"sessions": {}})


def create_session():
    token = secrets.token_hex(32)
    created_at = _now().isoformat()
    expires_at = (_now() + timedelta(days=SESSION_LIFETIME_DAYS)).isoformat()
    if db_backend.IS_POSTGRES:
        with storage.get_conn() as conn:
            conn.execute(
                "INSERT INTO auth_sessions (token, created_at, expires_at) VALUES (?, ?, ?)",
                (token, created_at, expires_at),
            )
        return token
    sessions = _load_sessions()
    sessions["sessions"][token] = {"created_at": created_at, "expires_at": expires_at}
    base_config.save_config(_SESSIONS_FILE, sessions)
    return token


def is_valid_session(token):
    if not token:
        return False
    if db_backend.IS_POSTGRES:
        with storage.get_conn() as conn:
            row = conn.execute(
                "SELECT expires_at FROM auth_sessions WHERE token = ?", (token,)
            ).fetchone()
        if not row:
            return False
        return _now() < datetime.fromisoformat(row[0])
    entry = _load_sessions()["sessions"].get(token)
    if not entry:
        return False
    return _now() < datetime.fromisoformat(entry["expires_at"])


def invalidate_session(token):
    if db_backend.IS_POSTGRES:
        with storage.get_conn() as conn:
            conn.execute("DELETE FROM auth_sessions WHERE token = ?", (token,))
        return
    sessions = _load_sessions()
    if token in sessions["sessions"]:
        del sessions["sessions"][token]
        base_config.save_config(_SESSIONS_FILE, sessions)
