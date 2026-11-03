"""Recovery decision: the Codex branch let anonymous visitors GET /preview and /api/quality/preview.
Those routes (and the whole Signal Control Room) were removed, and the login guard must not
exempt them if they ever come back."""


def test_preview_paths_are_not_login_exempt(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sindhu_web import security
    app = FastAPI()

    @app.get('/preview')
    def preview():
        return {'secret': 1}

    @app.get('/api/quality/preview')
    def api_preview():
        return {'secret': 1}

    app.middleware('http')(security.token_guard_middleware)
    monkeypatch.setattr(security.auth, 'is_valid_session', lambda t: False)
    c = TestClient(app, base_url='http://127.0.0.1', client=('127.0.0.1', 1234))
    assert c.get('/preview', follow_redirects=False).status_code == 307
    assert c.get('/api/quality/preview').status_code == 401
