"""Master plan A16 (P35): on Cloud the first account cannot be claimed by a stranger; DASHBOARD_PASSWORD (Render env) is an owner
login; /health stays public; protected routes need a session; existing accounts keep working."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(test_db, monkeypatch, tmp_path):
    from sindhu_web import security, auth
    monkeypatch.setattr(auth, "_CRED_FILE", f"auth_test_{tmp_path.name}.json")      # each test starts with no account
    from sindhu_web.api import auth as auth_api
    monkeypatch.setattr(security, "_is_lan_client", lambda h: True)
    auth_api._login_reset_for_tests() if hasattr(auth_api, "_login_reset_for_tests") else None
    import cloud_runtime.app as cloud
    return TestClient(cloud.app, follow_redirects=False)


def test_cloud_setup_without_env_password_is_refused(client, monkeypatch):
    from sindhu_web.api import auth as auth_api
    monkeypatch.setattr(auth_api, "_cloud_mode", lambda: True)
    monkeypatch.delenv("DASHBOARD_PASSWORD", raising=False)
    r = client.post("/api/auth/setup", json={"username": "x", "password": "stranger-pass-123"})
    assert r.status_code == 403 and "DASHBOARD_PASSWORD" in r.json()["detail"]


def test_cloud_setup_needs_the_env_password(client, monkeypatch):
    from sindhu_web.api import auth as auth_api
    monkeypatch.setattr(auth_api, "_cloud_mode", lambda: True)
    monkeypatch.setenv("DASHBOARD_PASSWORD", "owner-secret-xyz-1")
    assert client.post("/api/auth/setup", json={"username": "x", "password": "stranger-pass-123"}).status_code == 403
    assert client.post("/api/auth/setup", json={"username": "boss", "password": "owner-secret-xyz-1"}).status_code == 200


def test_env_password_logs_in_as_owner_and_wrong_one_does_not(client, monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", "owner-secret-xyz-1")
    assert client.get("/api/auth/status").json()["configured"] is True
    assert client.post("/api/auth/login", json={"username": "owner", "password": "wrong-password-1"}).status_code == 401
    r = client.post("/api/auth/login", json={"username": "owner", "password": "owner-secret-xyz-1"})
    assert r.status_code == 200
    cookie = r.headers.get("set-cookie", "").lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert client.get("/api/wallet").status_code == 200          # session works


def test_protected_routes_need_a_session_but_health_is_public(client):
    assert client.get("/api/wallet").status_code == 401
    assert client.get("/api/paper-trading/kill-switch/status").status_code == 401
    assert client.get("/health").status_code == 200 and client.head("/health").status_code == 200


def test_local_setup_is_unchanged(client, monkeypatch):
    from sindhu_web.api import auth as auth_api
    monkeypatch.setattr(auth_api, "_cloud_mode", lambda: False)
    monkeypatch.delenv("DASHBOARD_PASSWORD", raising=False)
    assert client.post("/api/auth/setup", json={"username": "me", "password": "local-pass-123"}).status_code == 200
