"""/health is what external pingers hit every few minutes on a 0.1 CPU host: it must answer without touching the database."""
import time

import pytest


def test_health_is_instant_has_commit_and_engine_flag_and_never_touches_the_database(test_db, monkeypatch):
    from fastapi.testclient import TestClient
    import cloud_runtime.app as cloud
    from data_engine import storage

    def boom(*a, **k):
        raise AssertionError("health must not open a database connection")

    monkeypatch.setattr(storage, "get_conn", boom)
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abcdef1234567890")
    c = TestClient(cloud.app)
    times = []
    for _ in range(40):
        t = time.perf_counter()
        r = c.get("/health")
        times.append(time.perf_counter() - t)
        assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["commit"] == "abcdef1" and "engine_running" in body and "started_at" in body
    times.sort()
    assert times[int(len(times) * 0.95) - 1] < 0.2        # p95 under 200 ms
