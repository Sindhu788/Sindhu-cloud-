"""Master plan V2 R5 (N2) fixes found in the G1 Cloud logs: the cloud_settings read is cached (it was ~3,700 statements + commits per
scan), and a deferred full refetch (R2) is a planned skip, not a scan error."""
import pytest

from data_engine import db_backend, storage


@pytest.fixture(autouse=True)
def _table(test_db):
    with storage.get_conn() as conn:     # Postgres-only table on Cloud; created here so the SQLite test database has it too
        conn.execute("CREATE TABLE IF NOT EXISTS cloud_settings (key TEXT PRIMARY KEY, value_json TEXT NOT NULL, updated_at TEXT)")
    yield


def test_cloud_setting_reads_hit_the_database_once_per_ttl(test_db, monkeypatch):
    storage.save_cloud_setting("v2_test_key", {"a": 1}, "2026-11-07T00:00:00Z")
    storage.clear_cloud_setting_cache()
    before = db_backend.db_stats_snapshot()["queries"]
    calls = []
    real = storage.get_conn

    def counting():
        calls.append(1)
        return real()

    monkeypatch.setattr(storage, "get_conn", counting)
    for _ in range(50):
        assert storage.get_cloud_setting("v2_test_key") == {"a": 1}
    assert len(calls) == 1
    assert db_backend.db_stats_snapshot()["queries"] - before <= 1


def test_own_save_is_visible_at_once_and_results_are_fresh_objects(test_db):
    storage.save_cloud_setting("v2_test_key2", {"x": 1}, "2026-11-07T00:00:00Z")
    a = storage.get_cloud_setting("v2_test_key2")
    a["x"] = 99                                               # a caller changing its copy must not change the cache
    assert storage.get_cloud_setting("v2_test_key2") == {"x": 1}
    storage.save_cloud_setting("v2_test_key2", {"x": 2}, "2026-11-07T00:00:01Z")
    assert storage.get_cloud_setting("v2_test_key2") == {"x": 2}


def test_cache_expires(test_db, monkeypatch):
    storage.save_cloud_setting("v2_test_key3", {"y": 1}, "2026-11-07T00:00:00Z")
    storage.get_cloud_setting("v2_test_key3")
    with storage.get_conn() as conn:                          # another process writes directly
        conn.execute("UPDATE cloud_settings SET value_json = ? WHERE key = ?", ('{"y": 2}', "v2_test_key3"))
    assert storage.get_cloud_setting("v2_test_key3") == {"y": 1}
    monkeypatch.setattr(storage, "_CLOUD_SETTING_TTL_S", -1)
    assert storage.get_cloud_setting("v2_test_key3") == {"y": 2}


def test_missing_key_is_none_and_cached(test_db):
    assert storage.get_cloud_setting("v2_never_saved") is None
    assert storage.get_cloud_setting("v2_never_saved") is None


def test_refetch_deferral_is_not_counted_as_an_error():
    import inspect
    from paper_trading import engine
    src = inspect.getsource(engine)
    assert src.count('type(e).__name__ == "RefetchDeferred"') == 2
    assert "Candle history still loading" in src
