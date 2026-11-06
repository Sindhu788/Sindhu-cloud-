"""Master plan V2 R5 (N2): scan-thread-only database counters, statement shapes, and the SELECT 1 latency probe."""
import threading

from data_engine import db_backend


def test_thread_scope_counts_only_this_thread():
    db_backend.thread_scope_begin()
    db_backend._db_note("query", 0.5, "SELECT  *" + chr(10) + "   FROM paper_positions WHERE id = ?")
    db_backend._db_note("commit", 0.25)
    t = threading.Thread(target=lambda: db_backend._db_note("query", 9.0, "SELECT other"))
    t.start(); t.join()
    mine, top = db_backend.thread_scope_end()
    assert mine["queries"] == 1 and mine["query_seconds"] == 0.5 and mine["commits"] == 1 and mine["commit_seconds"] == 0.25
    assert top == [("SELECT * FROM paper_positions WHERE id = ?", 1, 0.5)]
    assert all("other" not in s for s, _, _ in top)


def test_no_scope_no_thread_counting():
    db_backend.thread_scope_end()
    db_backend._db_note("query", 1.0, "SELECT 1")
    mine, top = db_backend.thread_scope_end()
    assert mine == {} and top == []


def test_probe_is_a_no_op_on_sqlite(monkeypatch):
    monkeypatch.setattr(db_backend, "IS_POSTGRES", False)
    assert db_backend.probe_latency(3) is None


def test_probe_measures_round_trips_with_a_fake_connection(monkeypatch):
    class Cur:
        def execute(self, sql): assert sql == "SELECT 1"
        def fetchone(self): return (1,)

    class Raw:
        def cursor(self): return Cur()
        def rollback(self): pass

    class Conn:
        _conn = Raw()
        def close(self): pass

    monkeypatch.setattr(db_backend, "IS_POSTGRES", True)
    monkeypatch.setattr(db_backend, "get_postgres_conn", lambda: Conn())
    r = db_backend.probe_latency(10)
    assert r["samples"] == 10 and r["p50_ms"] is not None and r["error"] is None
    assert db_backend.latency_state()["samples"] == 10


def test_health_details_has_db_latency():
    from paper_trading import self_check
    assert "db_latency" in self_check.details()
