"""Master plan V2 LG5 (L8) + DS3 (N4): login works both ways (env owner + saved account), never locks the owner out, rejects CSRF and
guessing; public endpoints stay public; HTML carries the security headers and no inline script; assets are fingerprinted, immutable,
compressed; the new pages and the old dashboard (/legacy) are served behind login."""
import os
import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sindhu_web", "static")


@pytest.fixture
def client(test_db, monkeypatch, tmp_path):
    from sindhu_web import security, auth, assets
    monkeypatch.setattr(auth, "_CRED_FILE", f"auth_v2_{tmp_path.name}.json")
    monkeypatch.setattr(auth, "_SESSIONS_FILE", f"sess_v2_{tmp_path.name}.json")
    monkeypatch.setattr(security, "_is_lan_client", lambda h: True)
    assets.reset()
    import cloud_runtime.app as cloud
    return TestClient(cloud.app, follow_redirects=False)


BROWSER = {"origin": "http://testserver", "sec-fetch-site": "same-origin"}


def _csrf(client):
    r = client.get("/api/auth/csrf")
    assert r.status_code == 200 and "httponly" in r.headers["set-cookie"].lower()
    return r.json()["csrf"]


def _login_owner(client, monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", "owner-secret-xyz-1")
    assert client.post("/api/auth/login", json={"username": "owner", "password": "owner-secret-xyz-1"}).status_code == 200


# ---------------------------------------------------------------- no lockout: both login paths work
def test_env_owner_login_works_from_a_browser_with_csrf(client, monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", "owner-secret-xyz-1")
    tok = _csrf(client)
    r = client.post("/api/auth/login", json={"username": "owner", "password": "owner-secret-xyz-1"}, headers={**BROWSER, "x-login-csrf": tok})
    assert r.status_code == 200
    assert client.get("/api/wallet").status_code == 200


def test_saved_account_login_works(client, monkeypatch):
    from sindhu_web import auth
    monkeypatch.delenv("DASHBOARD_PASSWORD", raising=False)
    auth.set_credentials("sindhu", "account-pass-123")
    tok = _csrf(client)
    r = client.post("/api/auth/login", json={"username": "sindhu", "password": "account-pass-123"}, headers={**BROWSER, "x-login-csrf": tok})
    assert r.status_code == 200


def test_wrong_password_and_wrong_username_get_the_same_generic_error(client):
    from sindhu_web import auth
    auth.set_credentials("sindhu", "account-pass-123")
    a = client.post("/api/auth/login", json={"username": "sindhu", "password": "nope-nope-1"})
    b = client.post("/api/auth/login", json={"username": "nobody", "password": "nope-nope-1"})
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


# ---------------------------------------------------------------- CSRF
def test_browser_login_without_csrf_is_rejected(client, monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", "owner-secret-xyz-1")
    r = client.post("/api/auth/login", json={"username": "owner", "password": "owner-secret-xyz-1"}, headers=BROWSER)
    assert r.status_code == 403


def test_cross_site_login_is_rejected_even_with_a_token(client, monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", "owner-secret-xyz-1")
    tok = _csrf(client)
    r = client.post("/api/auth/login", json={"username": "owner", "password": "owner-secret-xyz-1"},
                    headers={"origin": "https://evil.example", "x-login-csrf": tok})
    assert r.status_code == 403


# ---------------------------------------------------------------- guessing
def test_per_username_backoff_then_success_after_waiting(client, monkeypatch):
    from sindhu_web.api import auth as auth_api
    monkeypatch.setenv("DASHBOARD_PASSWORD", "owner-secret-xyz-1")
    for _ in range(3):
        assert client.post("/api/auth/login", json={"username": "owner", "password": "bad-guess-1"}).status_code == 401
    r = client.post("/api/auth/login", json={"username": "owner", "password": "owner-secret-xyz-1"})
    assert r.status_code == 429 and "Try again in" in r.json()["detail"]
    key = auth_api._user_key("owner")
    n, _ = auth_api._user_fails[key]
    auth_api._user_fails[key] = (n, 0.0)                         # the wait has passed
    assert client.post("/api/auth/login", json={"username": "owner", "password": "owner-secret-xyz-1"}).status_code == 200


def test_ip_rate_limit_still_triggers(client):
    for i in range(8):
        client.post("/api/auth/login", json={"username": f"u{i}", "password": "bad-guess-1"})
    assert client.post("/api/auth/login", json={"username": "zz", "password": "bad-guess-1"}).status_code == 429


# ---------------------------------------------------------------- sessions
def test_session_rotates_on_login_and_cookie_flags(client, monkeypatch):
    from sindhu_web import auth
    _login_owner(client, monkeypatch)
    old = client.cookies.get(auth.SESSION_COOKIE)
    r2 = client.post("/api/auth/login", json={"username": "owner", "password": "owner-secret-xyz-1"})
    cookie = r2.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert old and not auth.is_valid_session(old)


def test_idle_timeout_and_sliding_expiry(client):
    from sindhu_web import auth
    from data_engine import config as base_config
    tok = auth.create_session()
    assert auth.is_valid_session(tok)
    now = datetime.now(timezone.utc)
    s = auth._load_sessions()
    s["sessions"][tok]["expires_at"] = (now + timedelta(hours=1)).isoformat()         # last used 11 h ago
    base_config.save_config(auth._SESSIONS_FILE, s)
    assert auth.is_valid_session(tok)                                                 # still valid ... and extended
    assert datetime.fromisoformat(auth._load_sessions()["sessions"][tok]["expires_at"]) > now + timedelta(hours=11)
    s = auth._load_sessions()
    s["sessions"][tok]["expires_at"] = (now - timedelta(minutes=1)).isoformat()       # idle for more than 12 h
    base_config.save_config(auth._SESSIONS_FILE, s)
    assert not auth.is_valid_session(tok)


# ---------------------------------------------------------------- public vs protected
def test_public_endpoints_stay_public_and_others_need_login(client):
    assert client.get("/health").status_code == 200 and client.head("/health").status_code == 200
    assert client.get("/health/details").status_code == 200
    r = client.get("/api/public/login-scene")
    assert r.status_code == 200 and len(r.content) <= 4096
    body = r.json()
    assert set(body) == {"source", "symbol", "timeframe", "last_open_utc", "candles"} and len(body["candles"]) == 96
    assert all(0.0 <= v <= 1.0 for c in body["candles"] for v in c)
    for path in ("/api/wallet", "/api/summary", "/api/v2/system", "/api/v2/settings-schema", "/api/paper-trading/positions"):
        assert client.get(path).status_code == 401, path
    for path in ("/", "/legacy", "/ui-kit"):
        r = client.get(path)
        assert r.status_code in (302, 303, 307) and r.headers["location"].endswith("/login"), path


# ---------------------------------------------------------------- headers, no inline script
def test_html_has_security_headers(client):
    r = client.get("/login")
    assert r.status_code == 200
    csp = r.headers["content-security-policy"]
    assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp and "unsafe-eval" not in csp and "default-src 'self'" in csp
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["referrer-policy"] and r.headers["permissions-policy"]
    assert r.headers["cache-control"] == "no-cache"


@pytest.mark.parametrize("name", ["login.html", "app2.html", "index.html", "concepts.html", "activity_log.html"])
def test_no_inline_script_or_inline_handlers(name):
    html = open(os.path.join(STATIC, name), encoding="utf-8").read()
    for m in re.finditer(r"<script([^>]*)>(.*?)</script>", html, re.S):
        attrs, body = m.group(1), m.group(2).strip()
        assert "src=" in attrs or 'type="application/json"' in attrs, (name, attrs, body[:60])
    assert not re.search(r"\son(click|load|error|submit|change|input)=", html)


# ---------------------------------------------------------------- assets (DS3)
def test_assets_are_fingerprinted_immutable_and_compressed(client):
    html = client.get("/login").text
    assert "/static/css/" not in html and "/static/js/" not in html
    urls = re.findall(r'"(/assets/[^"]+)"', html)
    assert any(u.endswith(".css") for u in urls) and any("login.bundle." in u for u in urls)
    for u in urls[:6]:
        r = client.get(u, headers={"accept-encoding": "gzip"})
        assert r.status_code == 200, u
        assert r.headers["cache-control"] == "public, max-age=31536000, immutable"
        assert re.search(r"\.[0-9a-f]{10}\.", u)
    css_url = [u for u in urls if "/tokens." in u][0]
    r = client.get(css_url, headers={"accept-encoding": "gzip"})
    assert r.headers.get("content-encoding") == "gzip" and "/assets/vendor/fonts/inter-latin-wght-normal." in r.text
    assert client.get(css_url, headers={"if-none-match": r.headers["etag"]}).status_code == 304
    assert client.get("/assets/css/tokens.0000000000.css").status_code == 404


def test_asset_memory_stays_small():
    from sindhu_web import assets
    assets.reset()
    assert assets.memory_bytes() < 5 * 1024 * 1024


def test_build_tag_and_pages_behind_login(client, monkeypatch):
    _login_owner(client, monkeypatch)
    r = client.get("/")
    assert r.status_code == 200 and "v2.bundle." in r.text and '"sindhu-build"' in r.text and "{{BUILD}}" not in r.text
    leg = client.get("/legacy")
    assert leg.status_code == 200 and 'data-default-hash="wallet"' in leg.text and "/assets/js/app." in leg.text
    for path in ("/api/v2/system", "/api/v2/settings-schema", "/api/v2/validation", "/api/v2/benchmark", "/api/wallet/equity", "/api/summary"):
        assert client.get(path).status_code == 200, path


def test_wallet_settings_validate_with_the_self_check_limits(client, monkeypatch):
    _login_owner(client, monkeypatch)
    h = {"X-Sindhu-Token": client.get("/api/token").json()["token"]}
    assert client.post("/api/wallet/settings", json={"max_position_pct": 40}, headers=h).status_code == 422
    assert client.post("/api/wallet/settings", json={"risk_per_trade_pct": 3}, headers=h).status_code == 422
    r = client.post("/api/wallet/settings", json={"max_position_pct": 12}, headers=h)
    assert r.status_code == 200 and r.json()["settings"]["max_position_pct"] == 12
    from paper_trading import self_check
    assert "wallet.max_position_pct" not in self_check.validate_config()
