"""Grand Master Batch, Phase 7 Items 24, 25, 26, 27, 29, 30 -- the
remaining Sync batch items, all built on top of paper_trading/strategy_sync.py:

  24 -- selective sync: a push can optionally also carry the local
        paper_strategy_config row (enabled/priority/coins/market types),
        applied only to a genuinely first-time strategy_id.
  25 -- sync health check: LOCAL side compares its own library against
        what the cloud reports, flagging drift.
  26 -- offline queue: a push that fails with a network error is queued
        and later re-attempted by flush_offline_queue().
  27 -- sync timeline: the flat sync log bucketed into calendar days.
  29 -- bandwidth report: a running byte/push-count tally.
  30 -- emergency "cloud is source of truth" override: abandon a queued
        local push without contesting the cloud's copy.

Trades, history, and the rest of the database are never in scope for any
of this -- see strategy_sync.py's own module docstring; that boundary is
untouched by every item here.
"""
import sqlite3
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
import requests

from backtest_engine import strategy_library as lib
from backtest_engine.strategy_config import Condition, SLTPSpec, StrategyConfig
from data_engine import config as base_config, db_backend, storage
from paper_trading import strategy_sync


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


VALID_CONFIG_JSON = _valid_config().to_dict()


@pytest.fixture(autouse=True)
def isolated_library(tmp_path, monkeypatch):
    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path / "library"))
    yield


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(config_dir))
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
def cloud_mode(monkeypatch, tmp_path):
    """Same technique as tests/test_strategy_sync.py's own cloud_mode
    fixture -- a real sqlite3 file standing in for Postgres."""
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
    return db_path


# --------------------------------------------------------------- Item 24: selective sync

def test_push_without_include_settings_omits_the_settings_key(cloud_mode):
    sid = lib.create(_valid_config())
    fake_response = MagicMock(status_code=200)
    fake_response.json.return_value = {"ok": True}
    with patch("requests.post", return_value=fake_response) as mock_post:
        strategy_sync.push_strategy_to_cloud(sid, cloud_url="https://example.invalid", sync_secret="s3cr3t")
    assert "settings" not in mock_post.call_args.kwargs["json"]


def test_push_with_include_settings_carries_local_config(cloud_mode):
    sid = lib.create(_valid_config())
    storage.save_paper_strategy_config(sid, True, 3, ["BTCUSDT"], ["spot"], "2026-01-01T00:00:00+00:00")
    fake_response = MagicMock(status_code=200)
    fake_response.json.return_value = {"ok": True}
    with patch("requests.post", return_value=fake_response) as mock_post:
        strategy_sync.push_strategy_to_cloud(sid, cloud_url="https://example.invalid", sync_secret="s3cr3t",
                                              include_settings=True)
    body = mock_post.call_args.kwargs["json"]
    assert body["settings"] == {"enabled": True, "priority": 3, "supported_coins": ["BTCUSDT"],
                                 "supported_market_types": ["spot"]}


def test_receive_applies_pushed_settings_only_for_a_first_time_strategy(cloud_mode):
    secret = strategy_sync.get_or_create_sync_secret()
    strategy_sync.receive_synced_strategy(
        "strat1", "Test Strategy", [], VALID_CONFIG_JSON, secret,
        settings={"enabled": False, "priority": 9, "supported_coins": ["ETHUSDT"], "supported_market_types": []},
    )
    cfg = storage.get_paper_strategy_config("strat1")
    assert cfg["enabled"] is False
    assert cfg["priority"] == 9
    assert cfg["supported_coins"] == ["ETHUSDT"]


def test_receive_never_overwrites_an_already_configured_strategys_settings(cloud_mode):
    secret = strategy_sync.get_or_create_sync_secret()
    strategy_sync.receive_synced_strategy("strat1", "Test Strategy", [], VALID_CONFIG_JSON, secret,
                                           local_version=1, local_updated_at="t1")
    storage.save_paper_strategy_config("strat1", False, 2, [], [], "2026-01-01T00:00:00+00:00")
    strategy_sync.receive_synced_strategy(
        "strat1", "Test Strategy", [], VALID_CONFIG_JSON, secret, local_version=2, local_updated_at="t2",
        settings={"enabled": True, "priority": 1, "supported_coins": [], "supported_market_types": []},
    )
    cfg = storage.get_paper_strategy_config("strat1")
    assert cfg["enabled"] is False and cfg["priority"] == 2


# --------------------------------------------------------------- Item 27: sync timeline

def test_timeline_buckets_events_by_calendar_day(cloud_mode):
    storage.record_audit_event(strategy_sync._AUDIT_ENTITY, "success", "a", "2026-03-10T08:00:00+00:00")
    storage.record_audit_event(strategy_sync._AUDIT_ENTITY, "success", "b", "2026-03-10T20:00:00+00:00")
    storage.record_audit_event(strategy_sync._AUDIT_ENTITY, "failed", "c", "2026-03-11T09:00:00+00:00")
    with patch("paper_trading.strategy_sync.datetime") as mock_dt:
        from datetime import datetime, timezone
        mock_dt.now.return_value = datetime(2026, 3, 12, tzinfo=timezone.utc)
        timeline = strategy_sync.get_sync_timeline(days=7)
    days = {b["day"]: len(b["events"]) for b in timeline}
    assert days.get("2026-03-10") == 2
    assert days.get("2026-03-11") == 1
    assert timeline[0]["day"] == "2026-03-11"  # most recent first


def test_timeline_excludes_events_older_than_the_window(cloud_mode):
    storage.record_audit_event(strategy_sync._AUDIT_ENTITY, "success", "old", "2020-01-01T00:00:00+00:00")
    timeline = strategy_sync.get_sync_timeline(days=7)
    assert all(b["day"] != "2020-01-01" for b in timeline)


# --------------------------------------------------------------- Item 29: bandwidth report

def test_bandwidth_stats_start_at_zero(cloud_mode):
    stats = strategy_sync.get_sync_bandwidth_stats()
    assert stats == {"total_bytes_sent": 0, "push_count": 0, "average_bytes_per_push": 0}


def test_a_successful_push_adds_to_the_running_bandwidth_total(cloud_mode):
    sid = lib.create(_valid_config())
    fake_response = MagicMock(status_code=200)
    fake_response.json.return_value = {"ok": True}
    with patch("requests.post", return_value=fake_response):
        result = strategy_sync.push_strategy_to_cloud(sid, cloud_url="https://example.invalid", sync_secret="s3cr3t")
    assert result["bytes_sent"] > 0
    stats = strategy_sync.get_sync_bandwidth_stats()
    assert stats["push_count"] == 1
    assert stats["total_bytes_sent"] == result["bytes_sent"]


def test_a_failed_push_never_counts_toward_bandwidth(cloud_mode):
    sid = lib.create(_valid_config())
    with patch("requests.post", side_effect=requests.RequestException("down")):
        strategy_sync.push_strategy_to_cloud(sid, cloud_url="https://example.invalid", sync_secret="s3cr3t")
    assert strategy_sync.get_sync_bandwidth_stats()["push_count"] == 0


# --------------------------------------------------------------- Items 26+30: offline queue

def test_a_network_failure_queues_the_strategy_for_later(cloud_mode):
    sid = lib.create(_valid_config())
    with patch("requests.post", side_effect=requests.RequestException("down")):
        strategy_sync.push_strategy_to_cloud(sid, cloud_url="https://example.invalid", sync_secret="s3cr3t")
    queued = strategy_sync.list_offline_queue()
    assert len(queued) == 1
    assert queued[0]["strategy_id"] == sid


def test_flush_delivers_a_queued_push_once_the_cloud_is_reachable_again(cloud_mode):
    sid = lib.create(_valid_config())
    with patch("requests.post", side_effect=requests.RequestException("down")):
        strategy_sync.push_strategy_to_cloud(sid, cloud_url="https://example.invalid", sync_secret="s3cr3t")
    assert len(strategy_sync.list_offline_queue()) == 1

    fake_response = MagicMock(status_code=200)
    fake_response.json.return_value = {"ok": True}
    with patch("requests.post", return_value=fake_response):
        result = strategy_sync.flush_offline_queue(cloud_url="https://example.invalid", sync_secret="s3cr3t")
    assert result["flushed"] == [sid]
    assert strategy_sync.list_offline_queue() == []


def test_flush_keeps_an_item_queued_if_still_unreachable(cloud_mode):
    sid = lib.create(_valid_config())
    with patch("requests.post", side_effect=requests.RequestException("down")):
        strategy_sync.push_strategy_to_cloud(sid, cloud_url="https://example.invalid", sync_secret="s3cr3t")
        result = strategy_sync.flush_offline_queue(cloud_url="https://example.invalid", sync_secret="s3cr3t")
    assert result["still_queued"] == [sid]
    assert len(strategy_sync.list_offline_queue()) == 1


def test_flush_drops_an_item_that_fails_for_a_real_non_network_reason(cloud_mode):
    sid = lib.create(_valid_config())
    with patch("requests.post", side_effect=requests.RequestException("down")):
        strategy_sync.push_strategy_to_cloud(sid, cloud_url="https://example.invalid", sync_secret="s3cr3t")
    rejected = MagicMock(status_code=400, text='{"error": "validation failed"}')
    with patch("requests.post", return_value=rejected):
        result = strategy_sync.flush_offline_queue(cloud_url="https://example.invalid", sync_secret="s3cr3t")
    assert result["dropped"] == [sid]
    assert strategy_sync.list_offline_queue() == []


def test_emergency_override_discards_a_queued_push_without_retrying_it(cloud_mode):
    sid = lib.create(_valid_config())
    with patch("requests.post", side_effect=requests.RequestException("down")):
        strategy_sync.push_strategy_to_cloud(sid, cloud_url="https://example.invalid", sync_secret="s3cr3t")
    assert len(strategy_sync.list_offline_queue()) == 1

    removed = strategy_sync.discard_from_offline_queue(sid)
    assert removed is True
    assert strategy_sync.list_offline_queue() == []
    # discarding a second time (nothing left) is a harmless no-op, not an error
    assert strategy_sync.discard_from_offline_queue(sid) is False


# --------------------------------------------------------------- Item 25: sync health check

def test_health_check_reports_unreachable_with_no_secret_configured():
    result = strategy_sync.check_sync_health()
    assert result["reachable"] is False


def test_health_check_flags_a_strategy_that_is_out_of_sync():
    strategy_sync.save_sync_target(cloud_url="https://example.invalid", sync_secret="s3cr3t")
    sid = lib.create(_valid_config())
    lib.save_version(sid, _valid_config("Updated Name"))  # bumps current_version to 2

    fake_response = MagicMock(status_code=200)
    fake_response.json.return_value = {"synced": {sid: {"local_version": 1, "synced_at": "t1"}}}
    with patch("requests.get", return_value=fake_response):
        result = strategy_sync.check_sync_health()

    assert result["reachable"] is True
    assert len(result["out_of_sync"]) == 1
    assert result["out_of_sync"][0]["strategy_id"] == sid
    assert result["out_of_sync"][0]["cloud_version"] == 1


def test_health_check_reports_in_sync_when_versions_match():
    strategy_sync.save_sync_target(cloud_url="https://example.invalid", sync_secret="s3cr3t")
    sid = lib.create(_valid_config())

    fake_response = MagicMock(status_code=200)
    fake_response.json.return_value = {"synced": {sid: {"local_version": 1, "synced_at": "t1"}}}
    with patch("requests.get", return_value=fake_response):
        result = strategy_sync.check_sync_health()

    assert result["in_sync"] == [sid]
    assert result["out_of_sync"] == []


def test_health_check_reports_network_error_honestly():
    strategy_sync.save_sync_target(cloud_url="https://example.invalid", sync_secret="s3cr3t")
    with patch("requests.get", side_effect=requests.RequestException("down")):
        result = strategy_sync.check_sync_health()
    assert result["reachable"] is False
    assert "network error" in result["error"]
