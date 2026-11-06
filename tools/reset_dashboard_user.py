"""Master plan V2 R10 (N5 + P35): owner tool to see or reset the dashboard login. Never prints a password or a hash.

    python -m tools.reset_dashboard_user --list                    # local account: shows the username only
    python -m tools.reset_dashboard_user --reset <username>        # local: asks twice for a new password (hidden), saves its hash
    python -m tools.reset_dashboard_user --list --cloud            # Cloud database (DATABASE_URL from the local, git-ignored .env)
    python -m tools.reset_dashboard_user --reset <username> --cloud

There is one dashboard account. `--reset <username>` sets that account's username to <username> and its password to the new one.
All existing login sessions are signed out. The env login (`owner` + DASHBOARD_PASSWORD on Render) is not touched and keeps working.
--cloud only runs when the owner passes it; DATABASE_URL is read from .env in the repo folder (or the environment) and never printed."""
import argparse
import getpass
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _read_dotenv_url(path=None):
    path = path or os.path.join(ROOT, ".env")
    url = os.environ.get("DATABASE_URL", "")
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("DATABASE_URL="):
                    url = line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return url


def _ask_password(ask=getpass.getpass):
    p1 = ask("New password (min 8 characters, hidden): ")
    if len(p1) < 8:
        raise SystemExit("Password too short: at least 8 characters. Nothing was changed.")
    p2 = ask("Same password again: ")
    if p1 != p2:
        raise SystemExit("The two passwords are different. Nothing was changed.")
    return p1


# ---------------------------------------------------------------- local (SQLite / JSON file, the laptop)
def local_username():
    from sindhu_web import auth
    return auth._current_username()


def local_reset(username, password):
    from sindhu_web import auth
    from data_engine import config as base_config
    auth.set_credentials(username, password)
    try:
        base_config.save_config(auth._SESSIONS_FILE, {"sessions": {}})     # sign out every old session
    except Exception:
        pass


# ---------------------------------------------------------------- Cloud (Neon Postgres, only with --cloud)
def _pg_connect(url):
    try:
        import psycopg2
        return psycopg2.connect(url, connect_timeout=15)
    except ImportError:
        import psycopg
        return psycopg.connect(url, connect_timeout=15)


def cloud_username(url):
    conn = _pg_connect(url)
    try:
        cur = conn.cursor()
        cur.execute("SELECT username FROM auth_credentials WHERE id = 1")
        row = cur.fetchone()
        return row[0] if row else ""
    finally:
        conn.close()


def cloud_reset(url, username, password):
    from sindhu_web import auth
    salt_hex, hash_hex = auth._hash_password(password)
    conn = _pg_connect(url)
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO auth_credentials (id, username, salt, password_hash, updated_at) VALUES (1, %s, %s, %s, %s) "
            "ON CONFLICT (id) DO UPDATE SET username = EXCLUDED.username, salt = EXCLUDED.salt, "
            "password_hash = EXCLUDED.password_hash, updated_at = EXCLUDED.updated_at",
            (username, salt_hex, hash_hex, datetime.now(timezone.utc).isoformat()))
        cur.execute("DELETE FROM auth_sessions")          # sign out every old session (same transaction)
        conn.commit()
    finally:
        conn.close()


def main(argv=None, ask=getpass.getpass, out=print):
    ap = argparse.ArgumentParser(description="See or reset the SINDHU dashboard login (never prints passwords).")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--list", action="store_true", help="show the account's username")
    g.add_argument("--reset", metavar="USERNAME", help="set this username and a new password")
    ap.add_argument("--cloud", action="store_true", help="use the Cloud database (DATABASE_URL from the local .env)")
    a = ap.parse_args(argv)
    if a.cloud:
        url = _read_dotenv_url()
        if not url:
            raise SystemExit("--cloud needs DATABASE_URL in the local .env file (git-ignored). Nothing was changed.")
    if a.list:
        name = cloud_username(url) if a.cloud else local_username()
        where = "Cloud" if a.cloud else "local"
        out(f"{where} dashboard account: {name!r}" if name else f"{where}: no dashboard account saved yet")
        out("The env login also works on Cloud: username 'owner' + DASHBOARD_PASSWORD (Render > Environment).")
        return 0
    username = a.reset.strip()
    if not username:
        raise SystemExit("Username is empty. Nothing was changed.")
    password = _ask_password(ask)
    if a.cloud:
        cloud_reset(url, username, password)
    else:
        local_reset(username, password)
    out(f"Saved. Sign in as {username!r} with the new password. Old sessions are signed out.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
