import threading
import time

from paper_trading import memory_trim, stage_timer


class FakeLibc:
    def __init__(self, mallopt_result=1, trim_result=1):
        self.calls = []
        self._m, self._t = mallopt_result, trim_result

    def mallopt(self, param, value):
        self.calls.append(("mallopt", param, value)); return self._m

    def malloc_trim(self, pad):
        self.calls.append(("malloc_trim", pad)); return self._t


# ------------------------------------------------------------------ memory_trim
def test_cap_arenas_calls_mallopt_with_the_arena_max_constant(monkeypatch):
    monkeypatch.delenv("MALLOC_ARENA_MAX", raising=False); monkeypatch.delenv("SINDHU_MEMORY_TRIM", raising=False)
    lib = FakeLibc()
    assert memory_trim.cap_arenas(2, libc=lib) is True
    assert lib.calls == [("mallopt", -8, 2)]                          # M_ARENA_MAX is -8 in glibc


def test_cap_arenas_respects_an_existing_environment_setting_and_the_off_switch(monkeypatch):
    lib = FakeLibc()
    monkeypatch.setenv("MALLOC_ARENA_MAX", "4")
    assert memory_trim.cap_arenas(2, libc=lib) is False and lib.calls == []
    monkeypatch.delenv("MALLOC_ARENA_MAX"); monkeypatch.setenv("SINDHU_MEMORY_TRIM", "0")
    assert memory_trim.cap_arenas(2, libc=lib) is False and lib.calls == []


def test_cap_arenas_is_a_safe_no_op_when_there_is_no_libc(monkeypatch):
    monkeypatch.delenv("MALLOC_ARENA_MAX", raising=False); monkeypatch.delenv("SINDHU_MEMORY_TRIM", raising=False)
    assert memory_trim.cap_arenas(2, libc=None) in (True, False)       # on Windows/macOS: False; never raises


def test_release_memory_collects_and_trims_and_counts(monkeypatch):
    monkeypatch.delenv("SINDHU_MEMORY_TRIM", raising=False)
    before = memory_trim.stats()
    lib = FakeLibc()
    out = memory_trim.release_memory(libc=lib)
    assert out["trimmed"] is True and ("malloc_trim", 0) in lib.calls and out["seconds"] >= 0
    after = memory_trim.stats()
    assert after["calls"] == before["calls"] + 1 and after["trimmed"] == before["trimmed"] + 1


def test_release_memory_never_raises_even_if_libc_is_broken(monkeypatch):
    monkeypatch.delenv("SINDHU_MEMORY_TRIM", raising=False)

    class Broken:
        def malloc_trim(self, pad):
            raise OSError("boom")
    assert memory_trim.release_memory(libc=Broken())["trimmed"] is False


def test_release_memory_off_switch_does_nothing(monkeypatch):
    monkeypatch.setenv("SINDHU_MEMORY_TRIM", "off")
    lib = FakeLibc()
    assert memory_trim.release_memory(libc=lib) == {"skipped": True} and lib.calls == []


def test_release_memory_does_not_change_live_objects():
    data = {"a": list(range(1000))}
    memory_trim.release_memory(libc=FakeLibc())
    assert data["a"][-1] == 999


# ------------------------------------------------------------------ stage_timer
def test_stage_timer_accumulates_seconds_and_counts():
    t = stage_timer.StageTimer()
    with t.stage("a"):
        time.sleep(0.01)
    with t.stage("a"):
        pass
    t.add("b", 1.5)
    sec, cnt = t.snapshot()
    assert cnt == {"a": 2, "b": 1} and sec["a"] >= 0.009 and sec["b"] == 1.5
    s = t.summary(order=["b", "a"])
    assert s.startswith("b 1.5s x1") and "a " in s


def test_stage_timer_still_records_when_the_block_raises():
    t = stage_timer.StageTimer()
    try:
        with t.stage("boom"):
            raise ValueError("x")
    except ValueError:
        pass
    assert t.snapshot()[1] == {"boom": 1}


def test_stage_timer_is_thread_safe():
    t = stage_timer.StageTimer()

    def work():
        for _ in range(2000):
            t.add("x", 0.001)
    threads = [threading.Thread(target=work) for _ in range(8)]
    [th.start() for th in threads]; [th.join() for th in threads]
    sec, cnt = t.snapshot()
    assert cnt["x"] == 16000 and abs(sec["x"] - 16.0) < 1e-6


def test_delta_since_reports_only_stages_that_moved():
    t = stage_timer.StageTimer()
    t.add("a", 1.0); before = t.snapshot()[0]
    t.add("a", 2.0); t.add("b", 0.5); t.add("tiny", 0.0001)
    d = t.delta_since(before)
    assert d == {"a": 2.0, "b": 0.5}


def test_overhead_is_negligible_against_a_scan():
    """A scan has roughly 150 timed stages and about 8,000 database statements. Bound the cost per call generously (50 microseconds)."""
    # Day 8 fix: measured as THIS thread's CPU time (time.thread_time), best of 5 batches, so a busy machine (3 test shards in
    # parallel) cannot inflate it with wall-clock waiting. The 50 microsecond bound itself is unchanged.
    t = stage_timer.StageTimer()
    n = 5000
    best = float("inf")
    for _batch in range(5):
        t0 = time.thread_time()
        for _ in range(n):
            with t.stage("s"):
                pass
        best = min(best, (time.thread_time() - t0) / n)
    per_call = best
    assert per_call < 50e-6, f"{per_call * 1e6:.1f} microseconds per stage"


# ------------------------------------------------------------------ database counters
def test_database_counters_count_statements_commits_and_checkouts_without_changing_results():
    from data_engine import db_backend

    class Cur:
        description = None
        rowcount = 0

        def execute(self, sql, params=()):
            return None

        def executemany(self, sql, seq):
            return None

    class Raw:
        def cursor(self):
            return Cur()

        def commit(self):
            pass

    before = db_backend.db_stats_snapshot()
    conn = db_backend._PGConnection(Raw())
    conn.execute("select 1")
    conn.execute("select ?", (1,))
    conn.executemany("insert into t values (?)", [(1,), (2,)])
    conn.commit()
    d = {k: db_backend.db_stats_snapshot()[k] - before[k] for k in before}
    assert d["queries"] == 3 and d["commits"] == 1
    assert d["query_seconds"] >= 0 and "statements" in db_backend.db_stats_summary(before)
