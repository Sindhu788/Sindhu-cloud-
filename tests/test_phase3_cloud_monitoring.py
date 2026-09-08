"""Grand Master Prompt, Phase 3 (Cloud Monitoring Roadmap, remaining
items): Restart Analytics (3.13), API Monitor (3.11), Maintenance Mode
(3.7), Coin Manager / Priority (3.6), Active Signals (3.1, pure-function
math only -- no real exchange call in tests), Signal History (3.2), Export
Center (3.9), and Telegram Status Monitor's messages-today addition (3.3).
"""
import uuid
from datetime import datetime, timezone

import pytest

from data_engine import config as base_config
from data_engine import storage
from paper_trading import coin_priority, maintenance_mode
from sindhu_web import api_monitor
from sindhu_web.api import system


@pytest.fixture(autouse=True)
def isolated_local_config(tmp_path, monkeypatch):
    """maintenance_mode.py persists its state via base_config.load_or_seed/
    save_config (a JSON file, NOT the test_db-isolated SQLite DB) -- same
    isolation convention as tests/test_status_ping.py, needed for the same
    reason (otherwise state leaks across tests via the real data/config/
    directory)."""
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(config_dir))
    yield


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


# ------------------------------------------------------------ 3.13 Restart Analytics

def test_record_and_count_restarts(test_db):
    storage.record_server_restart("local", _now_iso())
    storage.record_server_restart("local", _now_iso())
    storage.record_server_restart("cloud", _now_iso())
    assert storage.count_server_restarts("local") == 2
    assert storage.count_server_restarts("cloud") == 1
    assert storage.count_server_restarts() == 3


def test_restart_analytics_endpoint_scopes_to_this_deployment(test_db, monkeypatch):
    monkeypatch.setattr("sindhu_web.security.CLOUD_MODE", False)
    storage.record_server_restart("local", "2026-01-01T00:00:00+00:00")
    storage.record_server_restart("local", "2026-01-01T01:00:00+00:00")
    storage.record_server_restart("cloud", "2026-01-01T02:00:00+00:00")
    result = system.get_restart_analytics()
    assert result["deployment"] == "local"
    assert result["restart_count"] == 2
    assert len(result["gaps_between_recent_restarts"]) == 1
    assert result["gaps_between_recent_restarts"][0]["gap_seconds"] == 3600


def test_restart_analytics_note_is_honest_about_scope(test_db):
    result = system.get_restart_analytics()
    assert "cannot tell a deliberate restart apart from a crash" in result["note"]


def test_record_startup_never_raises_even_if_storage_write_fails(test_db, monkeypatch):
    """Real incident: server_restart_log was missing from the curated
    Postgres schema, so storage.record_server_restart() raised on every
    single cloud boot -- and record_startup() is called synchronously,
    before yield, in cloud_runtime/app.py's lifespan, so that exception
    crashed the whole deploy's startup, not just this one feature. This is
    a monitoring side-effect, not a safety gate, so it must degrade to a
    log line instead of ever taking the app down again."""
    def _boom(*a, **k):
        raise Exception('relation "server_restart_log" does not exist')
    monkeypatch.setattr(storage, "record_server_restart", _boom)
    system.record_startup()  # must not raise


# ------------------------------------------------------------ 3.11 API Monitor

def test_api_monitor_tracks_total_and_failed_requests():
    api_monitor._state.update({"total_requests": 0, "failed_requests": 0, "total_duration_seconds": 0.0})
    api_monitor.record_request(200, 0.1)
    api_monitor.record_request(200, 0.3)
    api_monitor.record_request(500, 0.2)
    stats = api_monitor.get_stats()
    assert stats["total_requests"] == 3
    assert stats["failed_requests"] == 1
    assert stats["average_response_time_seconds"] == pytest.approx(0.2, abs=0.01)


def test_api_monitor_empty_state_has_no_average():
    api_monitor._state.update({"total_requests": 0, "failed_requests": 0, "total_duration_seconds": 0.0})
    stats = api_monitor.get_stats()
    assert stats["total_requests"] == 0
    assert stats["average_response_time_seconds"] is None


# ------------------------------------------------------------ 3.6 Coin Manager / Priority

def test_pin_and_demote_are_mutually_exclusive(test_db):
    coin_priority.pin("DOGEUSDT", "watching closely")
    result = coin_priority.list_all()
    assert result["pinned"][0]["symbol"] == "DOGEUSDT"
    assert result["demoted"] == []

    coin_priority.demote("DOGEUSDT", "changed my mind")
    result = coin_priority.list_all()
    assert result["pinned"] == []
    assert result["demoted"][0]["symbol"] == "DOGEUSDT"


def test_filter_out_demoted_removes_only_demoted_coins(test_db):
    coin_priority.demote("BADCOINUSDT")
    result = coin_priority.filter_out_demoted(["BTCUSDT", "BADCOINUSDT", "ETHUSDT"])
    assert result == ["BTCUSDT", "ETHUSDT"]


def test_ensure_pinned_included_adds_missing_pinned_coin_only_if_eligible(test_db):
    coin_priority.pin("PINNEDUSDT")
    shortlist = [{"symbol": "BTCUSDT", "score": 10}]
    result = coin_priority.ensure_pinned_included(shortlist, ["BTCUSDT", "PINNEDUSDT"])
    symbols = [e["symbol"] for e in result]
    assert "PINNEDUSDT" in symbols
    assert "BTCUSDT" in symbols
    assert len(result) == 2


def test_ensure_pinned_included_skips_pinned_coin_not_eligible(test_db):
    """A pinned coin that's blacklisted/delisted (not in eligible_symbols)
    must never be force-added -- pin is a priority boost, not an override
    of the blacklist."""
    coin_priority.pin("PINNEDUSDT")
    shortlist = [{"symbol": "BTCUSDT"}]
    result = coin_priority.ensure_pinned_included(shortlist, ["BTCUSDT"])  # PINNEDUSDT not eligible
    symbols = [e["symbol"] for e in result]
    assert "PINNEDUSDT" not in symbols


def test_ensure_pinned_included_never_duplicates_an_already_present_symbol(test_db):
    coin_priority.pin("BTCUSDT")
    shortlist = [{"symbol": "BTCUSDT", "score": 10}]
    result = coin_priority.ensure_pinned_included(shortlist, ["BTCUSDT"])
    assert len(result) == 1


def test_clear_coin_priority(test_db):
    coin_priority.pin("TEMPUSDT")
    coin_priority.clear("TEMPUSDT")
    result = coin_priority.list_all()
    assert result["pinned"] == []
    assert result["demoted"] == []


# ------------------------------------------------------------ 3.7 Maintenance Mode

def test_enter_and_exit_maintenance_mode_restores_prior_state(test_db, monkeypatch):
    from paper_trading.engine import engine
    from paper_trading import telegram_bot

    # A stateful fake -- is_running() must reflect stop()/start() actually
    # having been called, otherwise this test can't tell "exit correctly
    # restarted the engine" apart from "exit never checked is_running() at
    # all" (both would look identical against a hardcoded is_running=True).
    running = {"value": True}
    stop_calls = []
    start_calls = []
    monkeypatch.setattr(engine, "is_running", lambda: running["value"])
    monkeypatch.setattr(engine, "stop", lambda: (stop_calls.append(1), running.__setitem__("value", False)))
    monkeypatch.setattr(engine, "start", lambda *a, **k: (start_calls.append(1), running.__setitem__("value", True)))
    telegram_bot.save_settings(master_send_enabled=True)

    result = maintenance_mode.enter_maintenance_mode(actor="test")
    assert result["ok"] is True
    assert stop_calls == [1]
    assert telegram_bot.load_settings()["master_send_enabled"] is False
    assert maintenance_mode.get_state()["active"] is True

    result2 = maintenance_mode.exit_maintenance_mode(actor="test")
    assert result2["ok"] is True
    assert start_calls == [1]
    assert telegram_bot.load_settings()["master_send_enabled"] is True
    assert maintenance_mode.get_state()["active"] is False


def test_maintenance_mode_never_forces_telegram_back_on_if_it_was_already_off(test_db, monkeypatch):
    from paper_trading.engine import engine
    from paper_trading import telegram_bot

    monkeypatch.setattr(engine, "is_running", lambda: False)
    monkeypatch.setattr(engine, "start", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not start engine")))
    telegram_bot.save_settings(master_send_enabled=False)

    maintenance_mode.enter_maintenance_mode(actor="test")
    result = maintenance_mode.exit_maintenance_mode(actor="test")
    assert result["ok"] is True
    assert telegram_bot.load_settings()["master_send_enabled"] is False


def test_cannot_enter_maintenance_mode_twice(test_db, monkeypatch):
    from paper_trading.engine import engine
    monkeypatch.setattr(engine, "is_running", lambda: False)
    maintenance_mode.enter_maintenance_mode(actor="test")
    result = maintenance_mode.enter_maintenance_mode(actor="test")
    assert result["ok"] is False


def test_cannot_exit_maintenance_mode_when_not_active(test_db):
    result = maintenance_mode.exit_maintenance_mode(actor="test")
    assert result["ok"] is False


# ------------------------------------------------------------ 3.2 Signal History

def _seed_open_position(strategy_id="sidA", symbol="BTCUSDT"):
    with storage.get_conn() as conn:
        conn.execute(
            """INSERT INTO paper_positions
               (id, exchange, symbol, direction, entry_price, size, entry_time,
                strategy_id, strategy_name, status, created_at)
               VALUES (?, 'binance', ?, 'long', 100, 1, 0, ?, 'Test Strategy', 'open', ?)""",
            (uuid.uuid4().hex, symbol, strategy_id, _now_iso()),
        )


def _seed_closed_position(strategy_id, pnl, symbol="BTCUSDT"):
    with storage.get_conn() as conn:
        conn.execute(
            """INSERT INTO paper_positions
               (id, exchange, symbol, direction, entry_price, exit_price, size, entry_time, exit_time,
                pnl, pnl_pct, strategy_id, strategy_name, status, created_at, closed_at)
               VALUES (?, 'binance', ?, 'long', 100, 101, 1, 0, 1, ?, ?, ?, 'Test Strategy', 'closed', ?, ?)""",
            (uuid.uuid4().hex, symbol, pnl, pnl / 100, strategy_id, _now_iso(), _now_iso()),
        )


def test_signal_history_includes_running_win_loss_and_cancelled(test_db):
    from sindhu_web.api.paper_trading import get_signal_history

    _seed_open_position("sidA")
    _seed_closed_position("sidA", 10.0)
    _seed_closed_position("sidA", -5.0)
    storage.log_paper_decision({
        "exchange": "binance", "symbol": "ETHUSDT", "direction": "bullish", "decision": "rejected",
        "reason": "confluence too low", "created_at": _now_iso(),
    })

    result = get_signal_history()
    statuses = {r["signal_status"] for r in result["signals"]}
    assert statuses == {"running", "win", "loss", "cancelled"}


def test_signal_history_status_filter(test_db):
    from sindhu_web.api.paper_trading import get_signal_history

    _seed_closed_position("sidA", 10.0)
    _seed_closed_position("sidA", -5.0)
    result = get_signal_history(status="win")
    assert all(r["signal_status"] == "win" for r in result["signals"])
    assert len(result["signals"]) == 1


# ------------------------------------------------------------ 3.9 Export Center

def test_export_center_csv_contains_real_trade_rows(test_db):
    from sindhu_web.api.paper_trading import export_center_trades_csv

    _seed_closed_position("sidA", 42.0, symbol="ETHUSDT")
    response = export_center_trades_csv()
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]


def test_export_center_json_contains_real_trade_rows(test_db):
    from sindhu_web.api.paper_trading import export_center_trades_json

    _seed_closed_position("sidA", 42.0, symbol="ETHUSDT")
    response = export_center_trades_json()
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]


# ------------------------------------------------------------ 3.3 Telegram Status Monitor addition

def test_telegram_connection_status_reports_messages_sent_today(test_db):
    from sindhu_web.api.paper_trading import get_telegram_connection_status

    result = get_telegram_connection_status()
    assert "messages_sent_today" in result
    assert result["messages_sent_today"] == 0
