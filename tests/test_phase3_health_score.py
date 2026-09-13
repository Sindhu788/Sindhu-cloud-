"""Grand Master Batch, Phase 3 -- System Health Score.

Covers each of the 4 components (profitable ratio, Telegram delivery,
safety gates, PnL trend) in isolation, then the combined weighted score.
"""

from datetime import datetime, timedelta, timezone

import pytest

from data_engine import config as base_config, storage
from paper_trading import account_drawdown_guard, health_score, kill_switch, telegram_delivery


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------- profitable ratio

def test_profitable_ratio_with_no_classified_strategies_is_neutral(test_db):
    result = health_score._profitable_ratio_component()
    assert result["score"] == 50
    assert result["classified_count"] == 0


def test_profitable_ratio_counts_only_profitable_group(test_db):
    storage.upsert_paper_strategy_groups_batch(
        {"s1": "profitable", "s2": "profitable", "s3": "losing", "s4": "challenge"}, _now_iso(),
    )
    result = health_score._profitable_ratio_component()
    assert result["profitable_count"] == 2
    assert result["classified_count"] == 4
    assert result["score"] == 50.0


# --------------------------------------------------------------- telegram delivery

def test_telegram_component_scores_working_state_as_100(test_db, monkeypatch):
    monkeypatch.setattr(telegram_delivery, "connection_status",
                         lambda: {"state": "working", "reason": "fine"})
    result = health_score._telegram_component()
    assert result["score"] == 100


def test_telegram_component_scores_blocked_state_as_0(test_db, monkeypatch):
    monkeypatch.setattr(telegram_delivery, "connection_status",
                         lambda: {"state": "blocked", "reason": "network blocked"})
    result = health_score._telegram_component()
    assert result["score"] == 0


def test_telegram_component_scores_turned_off_as_neutral_not_penalized(test_db, monkeypatch):
    monkeypatch.setattr(telegram_delivery, "connection_status",
                         lambda: {"state": "turned_off", "reason": "off on purpose"})
    result = health_score._telegram_component()
    assert result["score"] == 50


# --------------------------------------------------------------- safety gates

def test_safety_gates_score_100_when_nothing_tripped(test_db):
    result = health_score._safety_gate_component()
    assert result["score"] == 100
    assert result["tripped"] == []


def test_safety_gates_score_0_when_kill_switch_active(test_db, monkeypatch):
    monkeypatch.setattr(kill_switch, "is_active", lambda: True)
    result = health_score._safety_gate_component()
    assert result["score"] == 0
    assert "kill switch" in result["detail"]


def test_safety_gates_score_0_when_account_drawdown_paused(test_db, monkeypatch):
    monkeypatch.setattr(account_drawdown_guard, "is_globally_paused", lambda: True)
    result = health_score._safety_gate_component()
    assert result["score"] == 0


def test_safety_gates_score_0_when_a_strategy_is_drawdown_paused(test_db):
    storage.set_strategy_paused("s1", True, "drawdown", _now_iso())
    result = health_score._safety_gate_component()
    assert result["score"] == 0
    assert "1 strategy(ies)" in result["detail"]


# --------------------------------------------------------------- pnl trend

def test_pnl_trend_neutral_with_no_recent_closed_trades(test_db):
    result = health_score._pnl_trend_component()
    assert result["score"] == 50
    assert result["recent_trade_count"] == 0


def test_pnl_trend_scores_100_for_positive_recent_pnl(test_db):
    storage.open_paper_position({
        "id": "p1", "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": int(datetime.now(timezone.utc).timestamp() * 1000),
        "created_at": _now_iso(), "strategy_id": "s1", "strategy_name": "Test",
    })
    storage.close_paper_position("p1", 110.0, _now_iso(), 10.0, 10.0, "take_profit", {}, {}, _now_iso())
    result = health_score._pnl_trend_component()
    assert result["score"] == 100
    assert result["recent_pnl"] == 10.0


def test_pnl_trend_scores_0_for_negative_recent_pnl(test_db):
    storage.open_paper_position({
        "id": "p1", "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": int(datetime.now(timezone.utc).timestamp() * 1000),
        "created_at": _now_iso(), "strategy_id": "s1", "strategy_name": "Test",
    })
    storage.close_paper_position("p1", 90.0, _now_iso(), -10.0, -10.0, "stop_loss", {}, {}, _now_iso())
    result = health_score._pnl_trend_component()
    assert result["score"] == 0


def test_pnl_trend_ignores_trades_closed_before_the_window(test_db):
    old_time = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    storage.open_paper_position({
        "id": "p1", "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": int(datetime.now(timezone.utc).timestamp() * 1000),
        "created_at": old_time, "strategy_id": "s1", "strategy_name": "Test",
    })
    storage.close_paper_position("p1", 200.0, old_time, 100.0, 100.0, "take_profit", {}, {}, old_time)
    result = health_score._pnl_trend_component()
    assert result["recent_trade_count"] == 0
    assert result["score"] == 50


# --------------------------------------------------------------- combined score

def test_compute_combines_all_four_components_with_documented_weights(test_db, monkeypatch):
    monkeypatch.setattr(health_score, "_profitable_ratio_component", lambda: {"score": 100, "detail": "x"})
    monkeypatch.setattr(health_score, "_telegram_component", lambda: {"score": 100, "detail": "x"})
    monkeypatch.setattr(health_score, "_safety_gate_component", lambda: {"score": 100, "detail": "x"})
    monkeypatch.setattr(health_score, "_pnl_trend_component", lambda: {"score": 100, "detail": "x"})
    result = health_score.compute()
    assert result["score"] == 100
    assert result["color"] == "green"
    assert sum(health_score.WEIGHTS.values()) == 1.0


def test_compute_score_drops_hard_when_safety_gate_tripped(test_db, monkeypatch):
    monkeypatch.setattr(health_score, "_profitable_ratio_component", lambda: {"score": 100, "detail": "x"})
    monkeypatch.setattr(health_score, "_telegram_component", lambda: {"score": 100, "detail": "x"})
    monkeypatch.setattr(health_score, "_safety_gate_component", lambda: {"score": 0, "detail": "x"})
    monkeypatch.setattr(health_score, "_pnl_trend_component", lambda: {"score": 100, "detail": "x"})
    result = health_score.compute()
    # 100*.30 + 100*.20 + 0*.30 + 100*.20 = 70
    assert result["score"] == 70
    assert result["color"] == "yellow"


def test_color_thresholds():
    assert health_score._color_for(80) == "green"
    assert health_score._color_for(60) == "yellow"
    assert health_score._color_for(30) == "red"
