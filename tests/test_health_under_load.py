"""Day 4: /health must answer in < 1 s even while the database is slow and other requests are being served."""
import threading
import time

from fastapi.testclient import TestClient


def test_health_is_not_blocked_by_a_slow_session_lookup(test_db, monkeypatch):
    import cloud_runtime.app as cloud
    from sindhu_web import auth

    def slow_session(token):
        time.sleep(2.5)                 # a Neon compute waking up / a slow query
        return False

    from sindhu_web import security
    monkeypatch.setattr(security, "CLOUD_MODE", True)     # the LAN gate is skipped in cloud mode; requests reach the session lookup
    monkeypatch.setattr(auth, "is_valid_session", slow_session)
    c = TestClient(cloud.app)
    c.get("/health")                    # warm-up: first call imports lazily; a running server has long done that
    results = []

    def hit_dashboard():
        results.append(c.get("/api/paper-trading/status").status_code)

    threads = [threading.Thread(target=hit_dashboard) for _ in range(6)]
    [t.start() for t in threads]
    time.sleep(0.3)                     # the dashboard requests are now stuck inside the slow lookup
    lat = []
    for _ in range(10):
        t0 = time.perf_counter()
        assert c.get("/health").status_code == 200
        lat.append(time.perf_counter() - t0)
        time.sleep(0.05)
    [t.join() for t in threads]
    assert max(lat) < 1.0, f"/health took {max(lat):.2f}s while sessions were slow"
    assert results.count(401) == 6


def test_health_stays_fast_while_cpu_bound_work_runs_in_another_thread(test_db):
    import cloud_runtime.app as cloud
    stop = threading.Event()

    def burn():
        x = 0
        while not stop.is_set():
            x += sum(i * i for i in range(2000))

    t = threading.Thread(target=burn, daemon=True); t.start()
    c = TestClient(cloud.app)
    lat = []
    for _ in range(20):
        t0 = time.perf_counter(); c.get("/health"); lat.append(time.perf_counter() - t0)
    stop.set(); t.join()
    lat.sort()
    assert lat[int(len(lat) * 0.95) - 1] < 1.0
