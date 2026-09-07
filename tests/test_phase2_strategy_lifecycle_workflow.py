"""Grand Master Prompt, Phase 2 (Strategy Lifecycle + Workflow System):
2.1 Lifecycle Stage, 2.2 the 7-metric Strategy Comparison extension, 2.3
Failure Reason Report, and 2.4 the Auto-Downgrade Rule. Phase 2.7 (One-
Change-At-A-Time) has its own tests in test_regime_aware_evolution.py.
"""
import uuid
from datetime import datetime, timezone

import pytest

from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from backtest_engine import strategy_library as lib
from data_engine import storage
from paper_trading import auto_downgrade
from sindhu_web.api.strategy_lifecycle import _compute_lifecycle_stage, compute_failure_reasons
from sindhu_web.strategy_aggregate import compute_backtest_metrics_for_strategy


@pytest.fixture
def isolated_library(tmp_path, monkeypatch):
    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path / "library"))


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _make_strategy(name="Test Strategy"):
    cfg = StrategyConfig(
        name=name, timeframes={"entry": "1h"},
        entry_conditions=[Condition(type="indicator_compare", indicator="rsi", op="<", value=30.0)],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0), take_profit=SLTPSpec(type="fixed_pct", value=2.0),
        risk_pct=1.0,
    )
    return lib.create(cfg)


def _seed_batch_with_trades(strategy_name, trades):
    """trades: list of (symbol, pnl, exit_reason)."""
    batch_id = f"batch_{uuid.uuid4().hex[:8]}"
    now = _now_iso()
    storage.create_batch(batch_id, strategy_name, "binance", {"initial_balance": 1000.0}, now)
    wins = sum(1 for _, pnl, _ in trades if pnl > 0)
    gross_profit = sum(pnl for _, pnl, _ in trades if pnl > 0)
    gross_loss = sum(pnl for _, pnl, _ in trades if pnl < 0)
    storage.save_result(batch_id, "ALL", "1h", "completed", {
        "total_trades": len(trades), "wins": wins, "net_profit": sum(p for _, p, _ in trades),
        "gross_profit": gross_profit, "gross_loss": gross_loss, "max_drawdown_pct": 10.0,
    }, now)
    for i, (symbol, pnl, exit_reason) in enumerate(trades):
        storage.save_trades(batch_id, symbol, "1h", [{
            "trade_num": i, "side": "long", "entry_time": i, "entry_price": 100.0,
            "exit_time": i + 1, "exit_price": 100.0 + pnl, "size": 1.0, "pnl": pnl, "pnl_pct": pnl / 100,
            "exit_reason": exit_reason,
        }])
    storage.update_batch_status(batch_id, "completed", now)
    return batch_id


def _seed_closed_paper_trade(strategy_id, pnl, closed_at):
    with storage.get_conn() as conn:
        conn.execute(
            """INSERT INTO paper_positions
               (id, exchange, symbol, direction, entry_price, exit_price, size, entry_time, exit_time,
                pnl, pnl_pct, exit_reason, strategy_id, strategy_name, status, created_at, closed_at)
               VALUES (?, 'binance', 'BTCUSDT', 'long', 100, 101, 1, 0, 1, ?, ?, 'take_profit', ?, 'x',
                       'closed', ?, ?)""",
            (uuid.uuid4().hex, pnl, pnl / 100, strategy_id, closed_at, closed_at),
        )


# ------------------------------------------------------------ 2.1 Lifecycle Stage

def test_stage_created_not_backtested():
    stage = _compute_lifecycle_stage({"archived": False}, {"batch_id": None}, None, None, False, False)
    assert stage == "Created -- Not Yet Backtested"


def test_stage_backtested_awaiting_activation():
    stage = _compute_lifecycle_stage({"archived": False}, {"batch_id": "b1"}, {"enabled": False}, None, False, False)
    assert "Awaiting Paper Trading Activation" in stage


def test_stage_accumulating_trades():
    stage = _compute_lifecycle_stage(
        {"archived": False}, {"batch_id": "b1"}, {"enabled": True}, {"trades": 5, "total_pnl": 1.0}, False, False)
    assert "Accumulating Trades (5/25)" in stage


def test_stage_passing_live_candidate():
    stage = _compute_lifecycle_stage(
        {"archived": False}, {"batch_id": "b1"}, {"enabled": True}, {"trades": 30, "total_pnl": 12.5}, False, False)
    assert stage == "Performance Analysis -- Passing (Live-Candidate)"


def test_stage_needs_optimization_without_lineage():
    stage = _compute_lifecycle_stage(
        {"archived": False}, {"batch_id": "b1"}, {"enabled": True}, {"trades": 30, "total_pnl": -5.0}, False, False)
    assert stage == "Performance Analysis -- Needs Optimization"


def test_stage_evolution_escalated_with_lineage():
    stage = _compute_lifecycle_stage(
        {"archived": False}, {"batch_id": "b1"}, {"enabled": True}, {"trades": 30, "total_pnl": -5.0}, True, False)
    assert stage == "Evolution Escalated -- Generating Variants"


def test_stage_paused_overrides_accumulating():
    stage = _compute_lifecycle_stage(
        {"archived": False}, {"batch_id": "b1"}, {"enabled": True}, {"trades": 30, "total_pnl": -5.0}, False, True)
    assert "Paused" in stage


def test_stage_archived_overrides_everything():
    stage = _compute_lifecycle_stage(
        {"archived": True}, {"batch_id": "b1"}, {"enabled": True}, {"trades": 30, "total_pnl": 5.0}, False, False)
    assert stage == "Archived"


# ------------------------------------------------------------ 2.2 Backtest metrics for Compare

def test_backtest_metrics_for_strategy_computes_all_seven(test_db, isolated_library):
    sid = _make_strategy("Metrics Test Strategy")
    _seed_batch_with_trades("Metrics Test Strategy", [
        ("BTCUSDT", 50.0, "take_profit"), ("BTCUSDT", -20.0, "stop_loss"), ("ETHUSDT", 30.0, "take_profit"),
    ])
    result = compute_backtest_metrics_for_strategy(sid)
    assert result["available"] is True
    assert result["total_trades"] == 3
    assert result["net_pnl"] == 60.0
    assert result["win_rate_pct"] == pytest.approx(66.67, abs=0.01)
    assert result["avg_win"] == pytest.approx(40.0)
    assert result["avg_loss"] == pytest.approx(-20.0)
    assert result["profit_factor"] is not None


def test_backtest_metrics_unavailable_when_no_batch(test_db, isolated_library):
    sid = _make_strategy("No Batch Strategy")
    result = compute_backtest_metrics_for_strategy(sid)
    assert result == {"available": False}


# ------------------------------------------------------------ 2.3 Failure Reason Report

def test_failure_reasons_breaks_down_by_coin_and_exit_reason(test_db, isolated_library):
    sid = _make_strategy("Losing Strategy")
    _seed_batch_with_trades("Losing Strategy", [
        ("BTCUSDT", -30.0, "stop_loss"), ("BTCUSDT", -10.0, "stop_loss"),
        ("ETHUSDT", 15.0, "take_profit"),
    ])
    result = compute_failure_reasons(sid)
    assert result["available"] is True
    assert result["total_trades"] == 3
    assert result["net_pnl"] == -25.0
    coin_pnls = {r["symbol"]: r["pnl"] for r in result["by_coin"]}
    assert coin_pnls["BTCUSDT"] == -40.0
    assert coin_pnls["ETHUSDT"] == 15.0
    reason_pnls = {r["exit_reason"]: r["pnl"] for r in result["by_exit_reason"]}
    assert reason_pnls["stop_loss"] == -40.0
    assert reason_pnls["take_profit"] == 15.0
    assert result["market_regime_breakdown_available"] is False


def test_failure_reasons_reports_unavailable_honestly_when_no_backtest(test_db, isolated_library):
    sid = _make_strategy("Never Backtested Strategy")
    result = compute_failure_reasons(sid)
    assert result["available"] is False


def test_failure_reasons_unknown_strategy_returns_none(test_db, isolated_library):
    assert compute_failure_reasons("does-not-exist") is None


# ------------------------------------------------------------ 2.4 Auto-Downgrade Rule

def test_auto_downgrade_insufficient_trades_reports_unavailable(test_db):
    result = auto_downgrade.evaluate_strategy("sid1")
    assert result["available"] is False
    assert result["sample_size"] == 0


def test_auto_downgrade_flags_losing_strategy(test_db):
    now = _now_iso()
    for _ in range(60):
        _seed_closed_paper_trade("sid2", 5.0, now)
    for _ in range(40):
        _seed_closed_paper_trade("sid2", -10.0, now)
    result = auto_downgrade.evaluate_strategy("sid2", initial_balance=10000.0)
    assert result["available"] is True
    assert result["sample_size"] == 100
    assert result["downgraded"] is True
    assert result["profit_factor"] < 1.0


def test_auto_downgrade_does_not_flag_a_genuinely_profitable_strategy(test_db):
    now = _now_iso()
    for _ in range(70):
        _seed_closed_paper_trade("sid3", 10.0, now)
    for _ in range(30):
        _seed_closed_paper_trade("sid3", -5.0, now)
    result = auto_downgrade.evaluate_strategy("sid3", initial_balance=10000.0)
    assert result["downgraded"] is False


def test_auto_downgrade_never_touches_paper_strategy_config(test_db):
    """Confirms the rule only classifies/logs -- it must never disable,
    pause, or otherwise mutate the strategy's actual paper-trading config."""
    now = _now_iso()
    for _ in range(100):
        _seed_closed_paper_trade("sid4", -5.0, now)
    storage.save_paper_strategy_config("sid4", True, 5, [], [], now)
    before = storage.get_paper_strategy_config("sid4")
    auto_downgrade.check_and_log_if_changed("sid4")
    after = storage.get_paper_strategy_config("sid4")
    assert before == after


def test_auto_downgrade_logs_audit_event_only_on_change(test_db):
    now = _now_iso()
    for _ in range(100):
        _seed_closed_paper_trade("sid5", -5.0, now)

    auto_downgrade.check_and_log_if_changed("sid5")
    first_count = storage.count_audit_trail()

    # Re-checking with the SAME underlying data (still downgraded) must not
    # add a second audit row.
    auto_downgrade.check_and_log_if_changed("sid5")
    assert storage.count_audit_trail() == first_count

    # Now genuinely improves -- must log exactly one new "RESTORED" event.
    for _ in range(100):
        _seed_closed_paper_trade("sid5", 20.0, now)
    auto_downgrade.check_and_log_if_changed("sid5")
    assert storage.count_audit_trail() == first_count + 1
    trail = storage.list_audit_trail(limit=5, entity="sid5")
    assert "RESTORED" in trail[0]["message"]


def test_auto_downgrade_state_persists_and_is_listable(test_db):
    now = _now_iso()
    for _ in range(100):
        _seed_closed_paper_trade("sid6", -5.0, now)
    auto_downgrade.check_and_log_if_changed("sid6")
    state = storage.get_paper_downgrade_state("sid6")
    assert state["downgraded"] is True
    all_states = storage.list_paper_downgrade_states()
    assert "sid6" in all_states
