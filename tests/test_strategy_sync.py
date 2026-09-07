"""Master Task Expansion, Part 1: Local -> Cloud Strategy Sync (config-only).
See paper_trading/strategy_sync.py's module docstring for the full design.

Same honest limitation as test_api_token_cloud_persistence.py/
test_cloud_settings_persistence.py: no real Postgres server is available
here -- a real sqlite3 file substitutes for storage.get_conn() wherever
db_backend.IS_POSTGRES is True. The actual network hop (requests.post) is
mocked at exactly that boundary -- everything on both sides of it (config
loading, validator/safety-check gating, cloud_settings storage, the
paper_strategy_config auto-registration, and the strategy_matcher merge)
runs for real, unmocked.
"""
import sqlite3
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from backtest_engine import strategy_library as lib
from backtest_engine.strategy_config import Condition, SLTPSpec, StrategyConfig
from data_engine import config as base_config, db_backend, storage
from paper_trading import strategy_matcher, strategy_sync


def _valid_config(name="Test Sync Strategy"):
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


def _broken_config(name="Broken Strategy"):
    """Fails validator.validate() outright: an unsupported timeframe."""
    cfg = _valid_config(name)
    cfg.timeframes = {"entry": "37fortnights"}
    return cfg


@pytest.fixture(autouse=True)
def isolated_library(tmp_path, monkeypatch):
    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path / "library"))
    yield


@pytest.fixture(autouse=True)
def isolated_local_config(tmp_path, monkeypatch):
    """Isolates the LOCAL-side settings (sync secret file, cloud_sync_target.json)
    from this project's real data/config/ directory."""
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
    """Simulates the CLOUD side: db_backend.IS_POSTGRES=True, backed by a
    real (but local, sqlite3-based) database standing in for Postgres --
    same technique as test_api_token_cloud_persistence.py's cloud_mode
    fixture, extended with the two extra tables this feature also touches
    (paper_strategy_config, audit_trail_log)."""
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


# ------------------------------------------------------------- secret

def test_sync_secret_is_stable_across_calls_on_cloud(cloud_mode):
    first = strategy_sync.get_or_create_sync_secret()
    second = strategy_sync.get_or_create_sync_secret()
    assert first == second
    assert len(first) >= 16


def test_sync_secret_survives_a_simulated_restart(cloud_mode, monkeypatch):
    secret = strategy_sync.get_or_create_sync_secret()
    monkeypatch.setattr(storage, "get_conn", _connect(cloud_mode))
    assert strategy_sync.get_or_create_sync_secret() == secret


def test_local_sync_secret_uses_a_local_file_not_cloud_settings():
    """db_backend.IS_POSTGRES defaults False in this process (no cloud_mode
    fixture applied) -- must never touch cloud_settings at all."""
    assert db_backend.IS_POSTGRES is False
    secret = strategy_sync.get_or_create_sync_secret()
    assert strategy_sync.get_or_create_sync_secret() == secret


# ------------------------------------------------------------- receive (cloud side)

def test_receive_rejects_wrong_secret(cloud_mode):
    expected = strategy_sync.get_or_create_sync_secret()
    result, status = strategy_sync.receive_synced_strategy(
        "abc123", "Some Strategy", [], _valid_config().to_dict(), "wrong-secret",
    )
    assert status == 401
    assert result["ok"] is False
    assert expected != "wrong-secret"


def test_receive_rejects_a_config_that_fails_the_validator(cloud_mode):
    secret = strategy_sync.get_or_create_sync_secret()
    result, status = strategy_sync.receive_synced_strategy(
        "bad001", "Broken Strategy", [], _broken_config().to_dict(), secret,
    )
    assert status == 400
    assert result["ok"] is False
    assert "errors" in result
    # must NOT have registered it for paper trading
    assert "bad001" not in storage.list_paper_strategy_configs()


def test_receive_accepts_a_valid_config_and_registers_it_enabled(cloud_mode):
    secret = strategy_sync.get_or_create_sync_secret()
    result, status = strategy_sync.receive_synced_strategy(
        "good001", "Good Strategy", ["swing"], _valid_config().to_dict(), secret,
    )
    assert status == 200
    assert result["ok"] is True
    assert result["newly_enabled"] is True

    configs = storage.list_paper_strategy_configs()
    assert configs["good001"]["enabled"] is True
    assert configs["good001"]["priority"] == 5

    synced = strategy_sync.get_synced_strategy("good001")
    assert synced["name"] == "Good Strategy"
    assert synced["config_json"]["name"] == "Test Sync Strategy"


def test_re_sync_never_clobbers_a_manually_changed_enabled_flag(cloud_mode):
    """A CEO who has since disabled a synced strategy on the cloud
    dashboard must not have that choice silently reverted by a later
    re-sync of an updated version."""
    secret = strategy_sync.get_or_create_sync_secret()
    strategy_sync.receive_synced_strategy("good002", "Good Strategy", [], _valid_config().to_dict(), secret)
    storage.save_paper_strategy_config("good002", enabled=False, priority=9,
                                        supported_coins=[], supported_market_types=[], now_iso="2026-01-01T00:00:00+00:00")

    result, status = strategy_sync.receive_synced_strategy(
        "good002", "Good Strategy v2", [], _valid_config("Good Strategy v2").to_dict(), secret,
    )
    assert status == 200
    assert result["newly_enabled"] is False
    configs = storage.list_paper_strategy_configs()
    assert configs["good002"]["enabled"] is False, "manual disable must survive a re-sync"
    assert configs["good002"]["priority"] == 9


def test_receive_logs_every_attempt_success_and_failure(cloud_mode):
    secret = strategy_sync.get_or_create_sync_secret()
    strategy_sync.receive_synced_strategy("ok01", "OK", [], _valid_config().to_dict(), secret)
    strategy_sync.receive_synced_strategy("bad02", "Bad", [], _broken_config().to_dict(), secret)
    strategy_sync.receive_synced_strategy("ok03", "OK3", [], _valid_config().to_dict(), "wrong")

    log = storage.list_audit_trail(limit=10, entity="strategy_sync")
    actions = {row["action"] for row in log}
    assert actions == {"success", "failed"}
    assert len(log) == 3


# ------------------------------------------------------------- push (local side)

def test_push_rejects_a_locally_broken_config_without_any_network_call():
    sid = lib.create(_broken_config())
    with patch("requests.post") as mock_post:
        result = strategy_sync.push_strategy_to_cloud(sid, cloud_url="https://example.invalid", sync_secret="s")
    assert result["ok"] is False
    assert "errors" in result
    mock_post.assert_not_called()
    log = strategy_sync.get_sync_log()
    assert log[0]["action"] == "failed"


def test_push_requires_a_configured_secret():
    sid = lib.create(_valid_config())
    result = strategy_sync.push_strategy_to_cloud(sid, cloud_url="https://example.invalid", sync_secret="")
    assert result["ok"] is False
    assert "secret" in result["error"]


def test_push_sends_the_small_config_only_and_reports_success():
    sid = lib.create(_valid_config())
    fake_response = MagicMock(status_code=200)
    fake_response.json.return_value = {"ok": True, "strategy_id": sid, "newly_enabled": True}
    with patch("requests.post", return_value=fake_response) as mock_post:
        result = strategy_sync.push_strategy_to_cloud(sid, cloud_url="https://example.invalid", sync_secret="s3cr3t")

    assert result["ok"] is True
    mock_post.assert_called_once()
    call = mock_post.call_args
    assert call.args[0] == "https://example.invalid/api/paper-trading/strategy-sync/push"
    assert call.kwargs["headers"]["X-Sindhu-Sync-Secret"] == "s3cr3t"
    body = call.kwargs["json"]
    assert body["strategy_id"] == sid
    assert body["config_json"]["name"] == "Test Sync Strategy"
    # never the backtest engine, evolution engine, or historical data -- just
    # the small config-shaped dict the payload actually is
    assert set(body.keys()) == {"strategy_id", "name", "tags", "config_json"}

    log = strategy_sync.get_sync_log()
    assert log[0]["action"] == "success"


def test_push_reports_a_cloud_side_rejection_honestly():
    sid = lib.create(_valid_config())
    fake_response = MagicMock(status_code=400, text='{"ok": false, "error": "validation failed"}')
    with patch("requests.post", return_value=fake_response):
        result = strategy_sync.push_strategy_to_cloud(sid, cloud_url="https://example.invalid", sync_secret="s3cr3t")
    assert result["ok"] is False
    assert "400" in result["error"]
    log = strategy_sync.get_sync_log()
    assert log[0]["action"] == "failed"


def test_push_handles_a_real_network_error_without_crashing():
    import requests
    sid = lib.create(_valid_config())
    with patch("requests.post", side_effect=requests.ConnectionError("boom")):
        result = strategy_sync.push_strategy_to_cloud(sid, cloud_url="https://example.invalid", sync_secret="s3cr3t")
    assert result["ok"] is False
    assert "network error" in result["error"]


# ------------------------------------------------------------- end-to-end bridge

def test_end_to_end_push_and_receive_wired_together(cloud_mode):
    """The strongest test in this file: a REAL local strategy, REAL
    validator/safety-check gating on BOTH sides, going through the REAL
    push_strategy_to_cloud() -> (mocked transport only) -> REAL
    receive_synced_strategy() -> REAL cloud_settings storage -> REAL
    strategy_matcher merge, proving a strategy built locally actually
    becomes tradeable on the "cloud" with zero shortcuts in between."""
    sid = lib.create(_valid_config("End To End Strategy"))
    secret = strategy_sync.get_or_create_sync_secret()

    def _bridge(url, json, headers, timeout):
        result, status = strategy_sync.receive_synced_strategy(
            json["strategy_id"], json["name"], json["tags"], json["config_json"],
            headers.get("X-Sindhu-Sync-Secret"),
        )
        resp = MagicMock(status_code=status, text=str(result))
        resp.json.return_value = result
        return resp

    with patch("requests.post", side_effect=_bridge):
        push_result = strategy_sync.push_strategy_to_cloud(sid, cloud_url="https://sindhu-cloud-1.onrender.com", sync_secret=secret)

    assert push_result["ok"] is True, push_result

    # Now prove the "cloud" paper-trading engine can actually see and would
    # trade it, via the real matching function -- not a re-implementation.
    matches = strategy_matcher.relevant_strategies("BTCUSDT", "trending")
    matched_ids = {m["strategy_id"] for m in matches}
    assert sid in matched_ids
    matched = next(m for m in matches if m["strategy_id"] == sid)
    assert matched["config"].name == "End To End Strategy"
