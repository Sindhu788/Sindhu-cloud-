"""Master plan A1 (P6 + S2): /health answers GET and HEAD with 200 without the database; paths that match no route (bot probes)
get a tiny 404 without a redirect, a template or a session/database lookup; real routes keep their old behaviour."""
import time

import pytest
from fastapi.testclient import TestClient

PROBES = ["/order", "/contact", "/wp-admin", "/admin", "/pricing", "/search", "/.env", "/wp-login.php", "/xmlrpc.php"]


def _no_db(monkeypatch):
    from data_engine import storage
    from sindhu_web import auth

    def boom(*a, **k):
        raise AssertionError("must not touch the database / session store")

    monkeypatch.setattr(storage, "get_conn", boom)
    monkeypatch.setattr(auth, "is_valid_session", boom)


@pytest.mark.parametrize("module", ["cloud_runtime.app", "sindhu_web.server"])
def test_health_get_and_head_are_200_without_database(test_db, monkeypatch, module):
    import importlib
    app = importlib.import_module(module).app
    c = TestClient(app)
    c.get("/health")                                   # warm-up (lazy imports)
    _no_db(monkeypatch)
    g = c.get("/health")
    h = c.head("/health")
    assert g.status_code == 200 and g.json()["status"] == "ok"
    assert h.status_code == 200
    assert h.content == b""                            # HEAD carries no body


def test_health_in_process_is_under_50ms(test_db, monkeypatch):
    """The handler's own cost, measured as this thread's CPU time (best of 30) so a busy test machine cannot inflate it."""
    import asyncio
    import cloud_runtime.app as cloud
    endpoint = next(r.endpoint for r in cloud.app.router.routes if getattr(r, "path", None) == "/health")
    asyncio.run(endpoint(None))                        # warm-up (lazy imports)
    _no_db(monkeypatch)
    best = float("inf")
    for _ in range(30):
        t = time.thread_time()
        body = asyncio.run(endpoint(None))
        best = min(best, time.thread_time() - t)
        assert body["status"] == "ok"
    assert best < 0.05, f"{best * 1000:.1f} ms"


@pytest.mark.parametrize("module", ["cloud_runtime.app", "sindhu_web.server"])
def test_unknown_paths_get_a_tiny_404_without_redirect_or_database(test_db, monkeypatch, module):
    import importlib
    app = importlib.import_module(module).app
    c = TestClient(app, follow_redirects=False)
    _no_db(monkeypatch)
    for p in PROBES:
        for method in ("HEAD", "GET", "POST"):
            r = c.request(method, p)
            assert r.status_code == 404, (method, p, r.status_code)
            assert "location" not in r.headers
            assert len(r.content) <= len(b"not found")


def test_known_routes_still_require_login(test_db, monkeypatch):
    """Unchanged behaviour for real routes: without a session, an API route answers 401 and a page route redirects to /login."""
    import cloud_runtime.app as cloud
    from sindhu_web import security
    monkeypatch.setattr(security, "_is_lan_client", lambda host: True)   # TestClient's host is the name "testclient", not an IP
    c = TestClient(cloud.app, follow_redirects=False)
    r = c.get("/api/nav")
    assert r.status_code == 401
    r = c.get("/login")
    assert r.status_code == 200
    r = c.get("/")
    assert r.status_code in (302, 307) and r.headers["location"].endswith("/login")
    r = c.get("/static/js/app.js")
    assert r.status_code == 200
