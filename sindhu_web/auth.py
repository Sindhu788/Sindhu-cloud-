"""Login gate (Master Task 2, Part 5) -- groundwork for eventual cloud
deployment, built now while the app is still LAN-only. A single-account
username/password login, stored hashed (PBKDF2-HMAC-SHA256, per-account
random salt -- never plaintext), gating every dashboard/API request via
security.py's middleware. This sits ON TOP OF the existing LAN-only +
state-changing-request token guard, not instead of it.

Sessions are a random token stored server-side (a small JSON file, same
pattern security.py already uses for its own token) with an expiry --
simple and sufficient for a single-user personal tool; no external auth
dependency needed.
"""

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

from data_engine import config as base_config

_CRED_FILE = "auth_credentials.json"
_SESSIONS_FILE = "auth_sessions.json"
_PBKDF2_ITERATIONS = 200_000
SESSION_LIFETIME_DAYS = 30

SESSION_COOKIE = "sindhu_session"


def _now():
    return datetime.now(timezone.utc)


def has_credentials():
    creds = base_config.load_or_seed(_CRED_FILE, {})
    return bool(creds.get("username") and creds.get("password_hash"))


def _hash_password(password, salt_hex=None):
    salt = bytes.fromhex(salt_hex) if salt_hex else os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return salt.hex(), digest.hex()


def set_credentials(username, password):
    salt_hex, hash_hex = _hash_password(password)
    base_config.save_config(_CRED_FILE, {
        "username": username, "salt": salt_hex, "password_hash": hash_hex,
        "updated_at": _now().isoformat(),
    })


def verify_password(username, password):
    creds = base_config.load_or_seed(_CRED_FILE, {})
    if not creds.get("username") or not creds.get("password_hash"):
        return False
    if username != creds["username"]:
        return False
    _, hash_hex = _hash_password(password, creds["salt"])
    return secrets.compare_digest(hash_hex, creds["password_hash"])


def change_password(current_password, new_password):
    creds = base_config.load_or_seed(_CRED_FILE, {})
    if not verify_password(creds.get("username", ""), current_password):
        return False
    set_credentials(creds["username"], new_password)
    return True


def _load_sessions():
    return base_config.load_or_seed(_SESSIONS_FILE, {"sessions": {}})


def create_session():
    token = secrets.token_hex(32)
    sessions = _load_sessions()
    sessions["sessions"][token] = {
        "created_at": _now().isoformat(),
        "expires_at": (_now() + timedelta(days=SESSION_LIFETIME_DAYS)).isoformat(),
    }
    base_config.save_config(_SESSIONS_FILE, sessions)
    return token


def is_valid_session(token):
    if not token:
        return False
    entry = _load_sessions()["sessions"].get(token)
    if not entry:
        return False
    return _now() < datetime.fromisoformat(entry["expires_at"])


def invalidate_session(token):
    sessions = _load_sessions()
    if token in sessions["sessions"]:
        del sessions["sessions"][token]
        base_config.save_config(_SESSIONS_FILE, sessions)
