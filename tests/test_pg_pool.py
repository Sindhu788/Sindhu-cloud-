import sys
import threading
import types

import pytest

from data_engine import db_backend as db


class FakeRaw:
    n = 0

    def __init__(self):
        FakeRaw.n += 1
        self.closed = 0
        self.rollbacks = 0
        self.fail_next = False

    def cursor(self):
        raw = self

        class C:
            def execute(self, sql, p=None):
                if raw.fail_next:
                    raw.fail_next = False
                    raise RuntimeError("server closed the connection")

            def fetchone(self):
                return (1,)
        return C()

    def rollback(self):
        self.rollbacks += 1

    def commit(self):
        pass

    def close(self):
        self.closed = 1


@pytest.fixture(autouse=True)
def fake_pg(monkeypatch):
    FakeRaw.n = 0
    mod = types.SimpleNamespace(connect=lambda url, connect_timeout=10, **keepalive_kw: FakeRaw())   # A6: keepalive kwargs
    monkeypatch.setitem(sys.modules, "psycopg2", mod)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
    monkeypatch.delenv("SINDHU_PG_POOL", raising=False)
    db._pool_close_all()
    db._pool_stats.update(opened=0, reused=0, dropped=0)
    yield
    db._pool_close_all()


def test_connections_are_reused_instead_of_opened_every_time():
    for _ in range(50):
        c = db.get_postgres_conn()
        c.close()
    assert FakeRaw.n == 1 and db.pool_stats()["reused"] == 49


def test_two_callers_at_once_never_share_a_connection_and_the_pool_is_bounded():
    held = [db.get_postgres_conn() for _ in range(7)]
    assert len({id(h._conn) for h in held}) == 7
    for h in held:
        h.close()
    assert db.pool_stats()["idle"] == db._POOL_MAX_IDLE and db.pool_stats()["dropped"] == 3


def test_returned_connection_is_rolled_back_and_broken_ones_are_discarded():
    c = db.get_postgres_conn()
    raw = c._conn
    c.close()
    assert raw.rollbacks >= 1
    c2 = db.get_postgres_conn()
    assert c2._conn is raw
    raw.closed = 1                      # server dropped it
    c2.close()
    assert db.pool_stats()["idle"] == 0
    c3 = db.get_postgres_conn()
    assert c3._conn is not raw


def test_an_idle_connection_is_checked_before_reuse_and_replaced_if_dead(monkeypatch):
    c = db.get_postgres_conn()
    raw = c._conn
    c.close()
    monkeypatch.setattr(db, "_POOL_CHECK_AFTER_S", -1)
    raw.fail_next = True                # the SELECT 1 health check fails
    c2 = db.get_postgres_conn()
    assert c2._conn is not raw and raw.closed == 1


def test_old_connections_are_retired(monkeypatch):
    c = db.get_postgres_conn()
    raw = c._conn
    monkeypatch.setattr(db, "_POOL_MAX_AGE_S", -1)
    c.close()
    assert raw.closed == 1 and db.pool_stats()["idle"] == 0


def test_pool_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("SINDHU_PG_POOL", "0")
    for _ in range(3):
        db.get_postgres_conn().close()
    assert FakeRaw.n == 3


def test_threads_hammering_the_pool_stay_consistent():
    errors = []

    def work():
        try:
            for _ in range(200):
                c = db.get_postgres_conn()
                c.close()
        except Exception as e:
            errors.append(e)

    ts = [threading.Thread(target=work) for _ in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert not errors and db.pool_stats()["idle"] <= db._POOL_MAX_IDLE
