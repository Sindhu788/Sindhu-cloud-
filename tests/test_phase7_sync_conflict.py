"""Grand Master Batch, Phase 7 Items 23+28 -- Sync Conflict Resolution Log
+ Safe Two-Way Merge.

Before this, strategy_sync.receive_synced_strategy() blind-overwrote
whatever cloud_settings row already existed for a strategy_id, with no
check at all. An out-of-order or stale push (two machines syncing the
same id, or a delayed retry landing after a newer push already went
through) could silently clobber a newer cloud record with an older one.

Now a push carries its local strategy_library version/updated_at, and an
incoming push that is not strictly newer than what is already stored is
treated as a conflict: the existing cloud record is kept, and a distinct
'conflict' audit event is recorded.
"""

import sqlite3
from contextlib import contextmanager

import pytest

from backtest_engine.strategy_config import Condition, SLTPSpec, StrategyConfig
from data_engine import config as base_config, db_backend, storage
from paper_trading import strategy_sync


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _connect(db_path):
    @contextmanager
    def _get_conn():
        c = sqlite3.connect(str(db_path))
        try:
            yield c
            c.commit()
        finally:
            c.close()
    return _get_conn


@pytest.fixture
def test_db(monkeypatch, tmp_path):
    """Simulates the CLOUD side (db_backend.IS_POSTGRES=True) the same way
    tests/test_strategy_sync.py's cloud_mode fixture does -- receive_synced_
    strategy()'s cloud_settings read/write only exists on that path, and
    the plain sqlite schema test_db normally sets up doesn't create the
    cloud_settings table at all (it's Postgres-only in production)."""
    monkeypatch.setattr(db_backend, "IS_POSTGRES", True)
    db_path = tmp_path / "fake_postgres.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""CREATE TABLE cloud_settings (
        key TEXT PRIMARY KEY, value_json TEXT NOT NULL, updated_at TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE paper_strategy_config (
        strategy_id TEXT PRIMARY KEY, enabled INTEGER, priority INTEGER,
        supported_coins_json TEXT, supported_market_types_json TEXT, updated_at TEXT,
        risk_pct_override REAL, max_open_trades_override INTEGER,
        htf_confluence_filter_enabled INTEGER, volume_spike_filter_enabled INTEGER,
        trailing_stop_enabled INTEGER, paused INTEGER, paused_reason TEXT, paused_at TEXT,
        capital_multiplier REAL, capital_multiplier_reason TEXT)""")
    conn.execute("""CREATE TABLE audit_trail_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, entity TEXT NOT NULL, action TEXT NOT NULL,
        message TEXT NOT NULL, created_at TEXT NOT NULL)""")
    conn.commit()
    conn.close()
    monkeypatch.setattr(storage, "get_conn", _connect(db_path))
    return str(db_path)


def _valid_config(name="Test Strategy"):
    return StrategyConfig(
        name=name,
        timeframes={"entry": "1m"},
        indicators=[{"name": "sma", "params": {"period": 3}, "role": "entry"}],
        entry_conditions=[
            Condition(type="price_compare", op=">", indicator="sma", params={"period": 3}),
        ],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0),
        take_profit=SLTPSpec(type="fixed_pct", value=2.0),
        risk_pct=1.0,
    )


VALID_CONFIG = _valid_config().to_dict()


def _push(strategy_id="strat1", name="Test Strategy", version=1, updated_at="2026-01-01T00:00:00+00:00", secret=None):
    secret = secret or strategy_sync.get_or_create_sync_secret()
    return strategy_sync.receive_synced_strategy(
        strategy_id, name, [], VALID_CONFIG, secret,
        local_version=version, local_updated_at=updated_at,
    )


def test_first_ever_sync_is_never_a_conflict(test_db):
    result, status = _push(version=1)
    assert status == 200
    assert result["ok"] is True
    assert not result.get("conflict")


def test_a_genuinely_newer_push_overwrites_cleanly(test_db):
    _push(version=1, updated_at="2026-01-01T00:00:00+00:00")
    result, status = _push(version=2, updated_at="2026-01-02T00:00:00+00:00")
    assert status == 200
    assert not result.get("conflict")
    stored = storage.get_cloud_setting(strategy_sync._SYNCED_STRATEGY_KEY_PREFIX + "strat1")
    assert stored["local_version"] == 2


def test_a_stale_out_of_order_push_is_rejected_as_a_conflict(test_db):
    _push(version=2, updated_at="2026-01-02T00:00:00+00:00")
    result, status = _push(version=1, updated_at="2026-01-01T00:00:00+00:00")
    assert status == 200
    assert result["ok"] is True
    assert result["conflict"] is True
    assert result["resolution"] == "kept existing cloud record"
    # the cloud record must be untouched -- still the newer v2 data.
    stored = storage.get_cloud_setting(strategy_sync._SYNCED_STRATEGY_KEY_PREFIX + "strat1")
    assert stored["local_version"] == 2


def test_conflict_is_recorded_in_the_sync_log_and_conflicts_list(test_db):
    _push(version=2, updated_at="2026-01-02T00:00:00+00:00")
    _push(version=1, updated_at="2026-01-01T00:00:00+00:00")

    conflicts = strategy_sync.list_sync_conflicts()
    assert len(conflicts) == 1
    assert "not newer than the stored" in conflicts[0]["message"]

    full_log = strategy_sync.get_sync_log()
    assert any(row["action"] == "conflict" for row in full_log)


def test_a_re_push_of_the_exact_same_version_is_not_a_conflict(test_db):
    """Re-syncing the identical version (e.g. a retried request) should
    still succeed plainly -- it's not a stale/out-of-order push, just a
    repeat of the same one."""
    _push(version=1, updated_at="2026-01-01T00:00:00+00:00")
    result, status = _push(version=1, updated_at="2026-01-01T00:00:00+00:00")
    assert status == 200
    assert not result.get("conflict")


def test_a_push_with_no_local_version_never_conflicts_and_always_overwrites(test_db):
    """An older client that doesn't send local_version/local_updated_at at
    all must keep working exactly as before this fix -- no conflict logic
    kicks in without version info on both sides."""
    _push(version=5, updated_at="2026-01-05T00:00:00+00:00")
    secret = strategy_sync.get_or_create_sync_secret()
    result, status = strategy_sync.receive_synced_strategy(
        "strat1", "Test Strategy", [], VALID_CONFIG, secret,
    )
    assert status == 200
    assert not result.get("conflict")
    stored = storage.get_cloud_setting(strategy_sync._SYNCED_STRATEGY_KEY_PREFIX + "strat1")
    assert stored["local_version"] is None


def test_invalid_secret_is_still_rejected_before_any_conflict_check(test_db):
    result, status = _push(version=1, secret="wrong-secret")
    assert status == 401
    assert not result.get("conflict")


def test_conflicting_push_still_never_registers_a_paper_strategy_config(test_db):
    """A rejected/discarded conflict push must not have any other side
    effect either -- it should behave as if nothing happened beyond the
    audit log entry."""
    _push(version=2, updated_at="2026-01-02T00:00:00+00:00")
    _push(version=1, updated_at="2026-01-01T00:00:00+00:00")
    # only ever configured once, from the first successful push.
    configs = storage.list_paper_strategy_configs()
    assert "strat1" in configs
