"""Regression tests for the 2026-09-16 hands-on audit batch:

1. Settings save: server-side validation (422 + per-field errors), change
   history recorded only for real changes, defaults endpoint.
2. /api/settings validation (the router is now also mounted on the cloud).
3. Cloud runtime mounts /api/settings and starts the daily report scheduler.
4. storage.get_symbol_time_bounds -- split MIN/MAX query, same results.
5. /api/paper-trading/risk-metrics-all -- batch path equals the per-strategy
   path, and is cached.
6. /api/paper-trading/confluence-open-positions -- one bulk, non-blocking
   response instead of one request per open position.
7. telegram_analytics.status_summary -- group totals reconcile with the
   Groups tab, unassigned books are surfaced, today's sends split by group.
8. Daily report contains the Overall / Group-wise / Telegram sections.
"""

import inspect
import time
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from data_engine import config as base_config, storage
from paper_trading import config as pt_config, insights, strategy_groups, telegram_analytics
from sindhu_web import cache
from sindhu_web.api import paper_trading as pt_api
from sindhu_web.api import settings as settings_api


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _close_a_trade(strategy_id, pnl, pos_id):
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    storage.open_paper_position({
        "id": pos_id, "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0, "entry_time": now_ms,
        "created_at": _now_iso(), "strategy_id": strategy_id, "strategy_name": "Test Strategy",
    })
    storage.close_paper_position(
        pos_id, exit_price=100.0 + pnl, exit_time=now_ms, pnl=pnl, pnl_pct=pnl,
        exit_reason="take_profit" if pnl > 0 else "stop_loss", lifecycle={}, reflection={},
        closed_at=_now_iso(), book_key=strategy_id,
    )


# --------------------------------------------------------------- 1. paper trading settings save

def test_validate_update_rejects_nonsense_values():
    errors = pt_config.validate_update({
        "initial_balance": -5, "risk_pct_default": 150, "max_open_trades": 0,
        "tick_interval_seconds": 2.5, "priority_rule": "coin_flip",
        "time_filter_block_start_utc": "25:00", "daily_goal_pct": "abc",
    })
    assert set(errors) == {"initial_balance", "risk_pct_default", "max_open_trades", "tick_interval_seconds",
                           "priority_rule", "time_filter_block_start_utc", "daily_goal_pct"}


def test_validate_update_accepts_real_values_and_ignores_none():
    assert pt_config.validate_update({
        "initial_balance": 100, "risk_pct_default": 0.5, "max_open_trades": 5, "cooldown_minutes": 0,
        "priority_rule": "win_rate", "opposite_signal_policy": "block", "daily_goal_pct": 0,
        "time_filter_block_end_utc": "07:30", "profit_lock_trail_pct": 100, "lookback_days": None,
    }) == {}


def test_update_settings_endpoint_returns_422_and_saves_nothing(test_db):
    before = pt_config.load()
    with pytest.raises(HTTPException) as exc:
        pt_api.update_settings(pt_api.SettingsUpdate(initial_balance=-1, daily_goal_pct=3.0))
    assert exc.value.status_code == 422
    assert "initial_balance" in exc.value.detail["errors"]
    after = pt_config.load()
    assert after["initial_balance"] == before["initial_balance"]
    assert after["daily_goal_pct"] == before["daily_goal_pct"]  # all-or-nothing, not a partial save
    assert pt_config.load_history() == []


def test_multi_field_save_persists_and_records_one_history_entry(test_db):
    saved = pt_api.update_settings(pt_api.SettingsUpdate(initial_balance=100.0, risk_pct_default=0.5))
    assert saved["initial_balance"] == 100.0 and saved["risk_pct_default"] == 0.5
    assert pt_config.load()["initial_balance"] == 100.0  # really persisted, not just echoed
    history = pt_api.get_settings_history()["entries"]
    assert len(history) == 1
    assert {c["field"] for c in history[0]["changes"]} == {"initial_balance", "risk_pct_default"}


def test_saving_identical_values_records_no_history(test_db):
    current = pt_config.load()
    pt_api.update_settings(pt_api.SettingsUpdate(initial_balance=current["initial_balance"]))
    assert pt_config.load_history() == []


def test_defaults_endpoint_returns_real_builtin_defaults(test_db):
    defaults = pt_api.get_settings_defaults()
    assert defaults["initial_balance"] == pt_config._DEFAULTS["initial_balance"]
    assert defaults["risk_pct_default"] == pt_config._DEFAULTS["risk_pct_default"]


# --------------------------------------------------------------- 2. /api/settings validation

def test_general_settings_rejects_invalid_values(test_db):
    with pytest.raises(HTTPException) as exc:
        settings_api.update_settings(settings_api.SettingsUpdate(default_risk_pct=0, refresh_speed_seconds=0, theme="neon"))
    assert exc.value.status_code == 422
    assert set(exc.value.detail["errors"]) == {"default_risk_pct", "refresh_speed_seconds", "theme"}


def test_general_settings_valid_save_persists(test_db):
    assert settings_api.update_settings(settings_api.SettingsUpdate(default_risk_pct=0.75, refresh_speed_seconds=20))["ok"]
    got = settings_api.get_settings()
    assert got["default_risk_pct"] == 0.75 and got["refresh_speed_seconds"] == 20


# --------------------------------------------------------------- 3. cloud runtime wiring

def test_cloud_runtime_mounts_settings_router_and_daily_report():
    import cloud_runtime.app as cloud_app
    paths = set()
    for route in cloud_app.app.routes:
        inner = getattr(route, "original_router", None)
        for r in (inner.routes if inner is not None else [route]):
            if getattr(r, "path", None):
                paths.add(r.path)
    assert "/api/settings" in paths
    assert "/api/paper-trading/telegram/status-summary" in paths
    assert "/api/paper-trading/confluence-open-positions" in paths
    assert "start_daily_report_scheduler_thread" in inspect.getsource(cloud_app._lifespan)


# --------------------------------------------------------------- 4. symbol time bounds

def test_symbol_time_bounds_split_query_matches_real_min_max(test_db):
    rows = [(t, 1, 1, 1, 1, 1, t + 59_999, 1, 1) for t in (60_000, 180_000, 120_000)]
    storage.insert_klines("binance", "BTCUSDT", rows)
    storage.insert_klines("binance", "ETHUSDT", [(999_000, 1, 1, 1, 1, 1, 1_058_999, 1, 1)])
    assert storage.get_symbol_time_bounds("binance", "BTCUSDT") == (60_000, 180_000)
    assert storage.get_symbol_time_bounds("binance", "NOPEUSDT") == (None, None)


# --------------------------------------------------------------- 5. risk metrics bulk

def test_risk_metrics_all_matches_per_strategy_computation(test_db, monkeypatch):
    for i, pnl in enumerate([5.0, -2.0, 3.0, -1.0]):
        _close_a_trade("stratA", pnl, f"a{i}")
    for i, pnl in enumerate([1.0, 2.0, -4.0]):
        _close_a_trade("stratB", pnl, f"b{i}")
    monkeypatch.setattr(pt_api.lib, "list_all", lambda: [{"id": "stratA"}, {"id": "stratB"}, {"id": "stratNone"}])
    got = pt_api.get_risk_metrics_all()["metrics"]
    since = insights.fresh_session_start()
    for sid in ("stratA", "stratB", "stratNone"):
        assert got[sid] == insights.compute_risk_metrics(sid, since=since)


# --------------------------------------------------------------- 6. confluence bulk endpoint

def test_confluence_open_positions_is_one_nonblocking_bulk_response(test_db, monkeypatch):
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    for pid in ("p1", "p2"):
        storage.open_paper_position({
            "id": pid, "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
            "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0, "entry_time": now_ms,
            "created_at": _now_iso(), "strategy_id": "stratA", "strategy_name": "Test Strategy",
        })
    monkeypatch.setattr(pt_api.confluence, "score_confluence", lambda *a, **k: {"passed": 2, "total": 3, "factors": []})
    first = pt_api.get_confluence_for_open_positions()
    assert first["ready"] is False and first["scores"] == {}  # never blocks the request
    deadline = time.time() + 10
    while time.time() < deadline:
        res = pt_api.get_confluence_for_open_positions()
        if res["ready"]:
            break
        time.sleep(0.05)
    assert res["ready"] is True
    assert res["scores"] == {"p1": {"passed": 2, "total": 3}, "p2": {"passed": 2, "total": 3}}


# --------------------------------------------------------------- 7. telegram status summary

def test_status_summary_reconciles_with_groups_and_surfaces_unassigned(test_db):
    _close_a_trade("winner", 4.0, "w1")
    _close_a_trade("winner", -1.0, "w2")
    _close_a_trade("loser", -3.0, "l1")
    _close_a_trade("orphan", 2.0, "o1")  # a book never assigned to any group
    now = _now_iso()
    storage.upsert_paper_strategy_group("winner", "profitable", now)
    storage.upsert_paper_strategy_group("loser", "losing", now)

    s = telegram_analytics.status_summary()
    groups = strategy_groups.all_group_summaries()
    for key in strategy_groups.GROUP_KEYS:
        assert s["groups"][key]["closed_trades"] == groups[key]["closed_trades"]
        assert s["groups"][key]["total_pnl"] == groups[key]["total_pnl"]
        assert s["groups"][key]["win_rate_pct"] == groups[key]["win_rate_pct"]
    assert s["overall"]["total_trades"] == 4
    assert s["overall"]["total_pnl"] == 2.0
    assert s["unassigned"] == {"closed_trades": 1, "total_pnl": 2.0}


def test_status_summary_counts_todays_sends_by_group(test_db):
    now = _now_iso()
    storage.upsert_paper_strategy_group("prof", "profitable", now)
    storage.upsert_paper_strategy_group("lose", "losing", now)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    for pid, sid in (("s1", "prof"), ("s2", "prof"), ("s3", "lose")):
        storage.open_paper_position({
            "id": pid, "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
            "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0, "entry_time": now_ms,
            "created_at": now, "strategy_id": sid, "strategy_name": sid,
        })
        storage.log_telegram_message(pid, sid, sid, "automatic", "signal", True, None, now)
    storage.log_telegram_message(None, None, None, "daily_report", "report", True, None, now)  # not a signal

    tg = telegram_analytics.status_summary()["telegram_today"]
    assert tg["sent"] == 3 and tg["pending"] == 3 and tg["won"] == 0 and tg["lost"] == 0
    assert tg["by_group"] == {"losing": 1, "profitable": 2, "challenge": 0, "unassigned": 0}


# --------------------------------------------------------------- 8. daily report sections

def test_daily_report_has_overall_group_and_telegram_sections(test_db, monkeypatch):
    from paper_trading import daily_report
    _close_a_trade("winner", 4.0, "w1")
    storage.upsert_paper_strategy_group("winner", "profitable", _now_iso())
    result = daily_report.generate_daily_report()
    text = result["report_text"]
    assert "1) Overall" in text and "2) Group-wise" in text and "3) Telegram" in text
    assert "Profitable: 1 trades" in text
    assert result["status_summary"]["overall"]["total_trades"] == 1


def test_global_search_skips_trade_scan_when_no_coin_matches(test_db, monkeypatch):
    """A non-coin term used to walk all ~3.4M backtest_trades rows (>300s
    measured). Trades are only matched by symbol, so no coin match = no scan."""
    from sindhu_web.api import search as search_api
    calls = []
    monkeypatch.setattr(search_api.storage, "load_symbols", lambda exchange: ["BTCUSDT", "ETHUSDT"])
    monkeypatch.setattr(search_api.storage, "search_trades", lambda q, limit=10: calls.append(q) or [{"symbol": "BTCUSDT"}])
    assert search_api.search("Ichimoku")["trades"] == []
    assert calls == []
    assert search_api.search("BTC")["trades"] == [{"symbol": "BTCUSDT"}]
    assert calls == ["BTC"]


def test_cache_is_cleared_between_tests_so_cached_endpoints_stay_isolated(test_db):
    assert cache._store == {}
