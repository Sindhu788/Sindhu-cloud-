"""Master plan V2 R1 (P5): the top-coins call has one overall deadline, short connect/read timeouts, and falls back to the last
good list on disk. Uses a real local HTTP server that answers slowly (injected slow server)."""
import http.server
import json
import threading
import time

import pytest
import requests

from data_engine import coingecko_client as cg


@pytest.fixture(autouse=True)
def _reset():
    cg._cache.update({"limit": None, "coins": None, "fetched_at": 0.0})
    yield
    cg._cache.update({"limit": None, "coins": None, "fetched_at": 0.0})


@pytest.fixture
def slow_server():
    delay = {"s": 5.0}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            time.sleep(delay["s"])
            body = json.dumps([{"id": "bitcoin", "symbol": "btc", "name": "Bitcoin", "market_cap_rank": 1}]).encode()
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    srv.daemon_threads = True
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    yield srv, delay
    srv.shutdown()
    srv.server_close()


def test_slow_server_hits_the_deadline_and_uses_the_disk_list(slow_server, monkeypatch):
    srv, delay = slow_server
    cg._save_disk_cache([{"id": "ethereum", "symbol": "eth", "name": "Ethereum", "market_cap_rank": 2, "extra": "dropped"}])
    monkeypatch.setattr(cg, "_BASE_URL", f"http://127.0.0.1:{srv.server_address[1]}")
    monkeypatch.setattr(cg, "_DEADLINE_S", 1.5)
    monkeypatch.setattr(cg, "_READ_TIMEOUT_S", 1.0)
    t0 = time.monotonic()
    coins = cg.get_top_market_cap_coins(limit=50)
    took = time.monotonic() - t0
    assert took < 3.0, took
    assert coins == [{"id": "ethereum", "symbol": "eth", "name": "Ethereum", "market_cap_rank": 2}]


def test_slow_server_without_any_saved_list_raises_quickly(slow_server, monkeypatch):
    srv, delay = slow_server
    monkeypatch.setattr(cg, "_BASE_URL", f"http://127.0.0.1:{srv.server_address[1]}")
    monkeypatch.setattr(cg, "_DEADLINE_S", 1.5)
    monkeypatch.setattr(cg, "_READ_TIMEOUT_S", 1.0)
    t0 = time.monotonic()
    with pytest.raises(requests.RequestException):
        cg.get_top_market_cap_coins(limit=50)
    assert time.monotonic() - t0 < 3.0


def test_a_good_fetch_is_saved_to_disk_with_a_timestamp(slow_server, monkeypatch):
    srv, delay = slow_server
    delay["s"] = 0.0
    monkeypatch.setattr(cg, "_BASE_URL", f"http://127.0.0.1:{srv.server_address[1]}")
    monkeypatch.setattr(cg.time, "sleep", lambda s: None)
    coins = cg.get_top_market_cap_coins(limit=1)
    assert coins[0]["symbol"] == "btc"
    info = cg.disk_cache_info()
    assert info["coins"] == 1 and info["saved_at_utc"].endswith("Z")


def test_timeouts_never_exceed_the_remaining_deadline(monkeypatch):
    seen = []

    def fake_get(url, params=None, timeout=None):
        seen.append(timeout)
        raise requests.ConnectTimeout("boom")

    monkeypatch.setattr(cg._session, "get", fake_get)
    with pytest.raises(requests.RequestException):
        cg._get_with_retry("http://x", {}, deadline=time.monotonic() + 3.0)
    assert seen and seen[0][0] <= 3.0 and seen[0][1] <= 3.0


def test_fallback_is_logged_once(monkeypatch, capsys):
    from paper_trading import log_dedup
    log_dedup.reset()

    def fake_get(url, params=None, timeout=None):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(cg._session, "get", fake_get)
    cg._save_disk_cache([{"id": "bitcoin", "symbol": "btc"}])
    for _ in range(3):
        cg._cache.update({"limit": None, "coins": None, "fetched_at": 0.0})
        cg.get_top_market_cap_coins(limit=1)
    out = capsys.readouterr().out
    assert out.count("top-coins fetch failed") == 1
