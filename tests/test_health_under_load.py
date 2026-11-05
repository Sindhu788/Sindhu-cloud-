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

    # Day 7 (deterministic version). Two things made the old test unreliable: (1) FastAPI's in-process TestClient bridges threads for every request, which
    # costs about 180 hand-offs of the Python lock at the 5 ms switch interval, so /health took about 0.9 s with a busy thread even on a quiet machine
    # (the old limit of 1.0 s was passed by luck); (2) wall-clock latency depends on what else the machine runs (other test shards, antivirus).
    # Now: the real app is served by a real uvicorn server on its OWN free local port (lifespan off: no engine, no scheduler), the requests come from a
    # SEPARATE process over a real socket (as in production), the busy thread runs in the server's process, and the limit is the original 1.0 s, scaled
    # up only when a quiet baseline measured in the same minute shows that the machine itself is slow. The structural test below does not depend on timing.
    import json
    import socket
    import subprocess
    import sys

    import uvicorn

    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    server = uvicorn.Server(uvicorn.Config(cloud.app, host="127.0.0.1", port=port, log_level="warning", lifespan="off"))
    th = threading.Thread(target=server.run, daemon=True); th.start()
    deadline = time.time() + 20
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    assert server.started, "test server did not start"
    client_code = (
        "import http.client, json, sys, time\n"
        "port, n = int(sys.argv[1]), int(sys.argv[2])\n"
        "out = []\n"
        "for _ in range(n):\n"
        "    t = time.perf_counter(); c = http.client.HTTPConnection('127.0.0.1', port, timeout=20); c.request('GET', '/health'); r = c.getresponse(); r.read(); c.close()\n"
        "    assert r.status == 200; out.append(time.perf_counter() - t)\n"
        "print(json.dumps(sorted(out)))\n")

    def sample(n=20):
        r = subprocess.run([sys.executable, "-c", client_code, str(port), str(n)], capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stderr[-300:]
        return json.loads(r.stdout.strip().splitlines()[-1])

    try:
        sample(3)                                                    # warm-up
        quiet = sample()
        baseline = quiet[len(quiet) // 2]
        t = threading.Thread(target=burn, daemon=True); t.start()
        try:
            busy = sample()
        finally:
            stop.set(); t.join()
    finally:
        server.should_exit = True; th.join(timeout=10)
    limit = max(1.0, 50 * baseline)
    p95 = busy[int(len(busy) * 0.95) - 1]
    assert p95 < limit, f"p95 {p95:.3f}s vs limit {limit:.3f}s (quiet median {baseline:.4f}s)"


def test_health_never_touches_the_database(test_db, monkeypatch):
    """Structural, load-independent guarantee behind the two timing tests: /health must answer even when every database call would fail."""
    import cloud_runtime.app as cloud
    from data_engine import storage

    def boom(*a, **k):
        raise AssertionError("/health must not open a database connection")

    c = TestClient(cloud.app)
    c.get("/health")
    monkeypatch.setattr(storage, "get_conn", boom)
    r = c.get("/health")
    assert r.status_code == 200 and r.json().get("status") == "ok"
