from fastapi.testclient import TestClient


def test_security_headers_on_every_response(test_db):
    import cloud_runtime.app as cloud
    c = TestClient(cloud.app)
    for path in ("/health", "/login", "/api/paper-trading/status"):
        r = c.get(path)
        assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
        assert r.headers["referrer-policy"] == "same-origin"


def test_login_is_throttled_per_client_and_expires(test_db, monkeypatch):
    import cloud_runtime.app as cloud
    from sindhu_web import auth
    from sindhu_web.api import auth as api
    monkeypatch.setattr(api, "_fails", {})
    from sindhu_web import security
    monkeypatch.setattr(security, "CLOUD_MODE", True)
    monkeypatch.setattr(auth, "verify_password", lambda u, p: p == "right-password-1")
    c = TestClient(cloud.app)
    h = {"x-forwarded-for": "203.0.113.9"}
    for i in range(api._LOGIN_MAX_PER_CLIENT):      # V2 LG4: a different username each try, so only the per-client limit is exercised
        assert c.post("/api/auth/login", json={"username": f"u{i}", "password": "bad"}, headers=h).status_code == 401
    assert c.post("/api/auth/login", json={"username": "u", "password": "right-password-1"}, headers=h).status_code == 429      # blocked even with the right password
    other = {"x-forwarded-for": "198.51.100.7"}
    api._user_fails.clear()     # master plan V2 LG4 (changed on purpose): the per-username backoff would also slow this username; here only the per-client limit is tested
    monkeypatch.setattr(auth, "create_session", lambda: "tok")
    assert c.post("/api/auth/login", json={"username": "u", "password": "right-password-1"}, headers=other).status_code == 200  # other client unaffected
    monkeypatch.setattr(api, "_LOGIN_WINDOW_S", -1)                                                                            # window over -> allowed again
    api._user_fails.clear()
    assert c.post("/api/auth/login", json={"username": "u", "password": "right-password-1"}, headers=h).status_code == 200


def test_session_cookie_is_secure_behind_https_and_always_httponly(test_db, monkeypatch):
    import cloud_runtime.app as cloud
    from sindhu_web import auth
    from sindhu_web.api import auth as api
    monkeypatch.setattr(api, "_fails", {})
    from sindhu_web import security
    monkeypatch.setattr(security, "CLOUD_MODE", True)
    monkeypatch.setattr(auth, "verify_password", lambda u, p: True)
    monkeypatch.setattr(auth, "create_session", lambda: "tok")
    c = TestClient(cloud.app)
    r = c.post("/api/auth/login", json={"username": "u", "password": "x"}, headers={"x-forwarded-proto": "https"})
    cookie = r.headers["set-cookie"].lower()
    assert "secure" in cookie and "httponly" in cookie and "samesite=lax" in cookie
