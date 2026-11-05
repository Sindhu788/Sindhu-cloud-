"""Master plan A6 (P4) + P40: connect retry, keepalives, fail-fast connect breaker; background-loop error dedup and backoff."""
import pytest

from data_engine import db_backend
from paper_trading import log_dedup


class FakeOperationalError(Exception):   # the name matters: only *OperationalError / OSError count as connect failures
    pass


@pytest.fixture
def breaker(monkeypatch):
    db_backend._breaker.update({"failures": 0, "open_until": 0.0, "opens": 0, "last_error": None})
    clock = [1000.0]
    import types
    monkeypatch.setattr(db_backend, "_time", types.SimpleNamespace(monotonic=lambda: clock[0], sleep=lambda s: None))
    logs = []
    monkeypatch.setattr(db_backend, "_breaker_log", logs.append)
    yield clock, logs
    db_backend._breaker.update({"failures": 0, "open_until": 0.0, "opens": 0, "last_error": None})


def test_one_quick_retry_then_success(breaker, monkeypatch):
    calls = []

    def connect():
        calls.append(1)
        if len(calls) == 1:
            raise FakeOperationalError("SSL SYSCALL error: EOF detected")
        return "conn"

    monkeypatch.setattr(db_backend, "_raw_connect", connect)
    assert db_backend._connect_with_breaker(sleep=lambda s: None) == "conn"
    assert len(calls) == 2 and db_backend.breaker_state()["consecutive_failures"] == 0


def test_breaker_opens_after_three_failed_connects_and_fails_fast_then_recovers(breaker, monkeypatch):
    clock, logs = breaker
    calls = []
    up = [False]

    def connect():
        calls.append(1)
        if not up[0]:
            raise FakeOperationalError("timeout expired")
        return "conn"

    monkeypatch.setattr(db_backend, "_raw_connect", connect)
    for _ in range(3):
        with pytest.raises(FakeOperationalError):
            db_backend._connect_with_breaker(sleep=lambda s: None)
    assert len(calls) == 6                                         # 3 callers x (attempt + one retry)
    st = db_backend.breaker_state()
    assert st["open"] and st["seconds_left"] == 30 and "timeout expired" in st["last_error"]
    assert any("OPEN for 30s" in l for l in logs)
    with pytest.raises(db_backend.DatabaseUnavailable):           # open: no network attempt at all
        db_backend._connect_with_breaker(sleep=lambda s: None)
    assert len(calls) == 6
    clock[0] += 31                                                 # cooldown over: one probe, still down -> 60 s
    with pytest.raises(FakeOperationalError):
        db_backend._connect_with_breaker(sleep=lambda s: None)
    assert db_backend.breaker_state()["seconds_left"] == 60
    clock[0] += 61
    up[0] = True                                                   # database back
    assert db_backend._connect_with_breaker(sleep=lambda s: None) == "conn"
    assert not db_backend.breaker_state()["open"] and db_backend.breaker_state()["consecutive_failures"] == 0
    assert any("reachable again" in l for l in logs)


def test_breaker_wait_is_capped_at_five_minutes(breaker, monkeypatch):
    clock, _ = breaker
    monkeypatch.setattr(db_backend, "_raw_connect", lambda: (_ for _ in ()).throw(FakeOperationalError("x")))
    for _ in range(12):
        clock[0] += 400
        with pytest.raises(FakeOperationalError):
            db_backend._connect_with_breaker(sleep=lambda s: None)
    assert db_backend.breaker_state()["seconds_left"] == 300


def test_connections_ask_for_tcp_keepalives(monkeypatch):
    seen = {}

    class FakePsycopg2:
        @staticmethod
        def connect(url, **kw):
            seen.update(kw)
            return "conn"

    import sys
    monkeypatch.setitem(sys.modules, "psycopg2", FakePsycopg2)
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pw@host/db")
    assert db_backend._raw_connect() == "conn"
    assert seen["keepalives"] == 1 and seen["keepalives_idle"] == 30 and seen["connect_timeout"] == 10


def test_dedup_logs_first_error_then_once_per_window_with_count():
    log_dedup.reset()
    out = []
    e = FakeOperationalError("connection failed: SSL SYSCALL error: EOF detected")
    for i in range(40):
        ok, n = log_dedup.should_log("telegram-commands", e, every=600, now=1000.0 + i * 60)
        if ok:
            out.append((i, n))
    assert out[0] == (0, 0)                     # first one always logged
    assert out[1] == (10, 9)                    # next one after 10 minutes, with the 9 suppressed
    assert len(out) == 4                        # 40 minutes -> 4 lines instead of 40


def test_dedup_keeps_different_error_kinds_and_sources_apart():
    log_dedup.reset()
    a = FakeOperationalError("x: SSL SYSCALL error: EOF detected")
    b = FakeOperationalError("x: timeout expired")
    assert log_dedup.should_log("s1", a, now=0)[0]
    assert log_dedup.should_log("s1", b, now=1)[0]
    assert log_dedup.should_log("s2", a, now=2)[0]
    assert not log_dedup.should_log("s1", a, now=3)[0]


def test_maybe_log_prints_original_text_and_suppressed_count():
    log_dedup.reset()
    out = []
    e = RuntimeError("boom")
    log_dedup.maybe_log(out.append, "src", e, "[src] failed: boom", every=600)
    for _ in range(5):
        log_dedup.maybe_log(out.append, "src", e, "[src] failed: boom", every=600)
    assert out == ["[src] failed: boom"]


def test_backoff_grows_and_caps():
    assert [log_dedup.backoff_seconds(n, base=5, cap=300) for n in range(0, 9)] == [0, 5, 10, 20, 40, 80, 160, 300, 300]
