"""GET /api/paper-trading/strategy-overview (sindhu_web/api/paper_trading.py)
-- powers the cloud dashboard's new "Strategies" page (Part 2 of the
cloud-fixes task). Calls the endpoint function directly rather than an HTTP
TestClient, same convention as test_clarification_page.py/test_wizard_api.py.
"""

from datetime import datetime, timezone

import pytest

from backtest_engine import strategy_library as lib
from backtest_engine.strategy_config import Condition, SLTPSpec, StrategyConfig
from data_engine import storage
from sindhu_web.api import paper_trading as pt_api


@pytest.fixture(autouse=True)
def isolated_library(tmp_path, monkeypatch):
    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path / "library"))


def _make_strategy(**overrides):
    base = dict(
        name="Overview Test Strategy",
        raw_text="test",
        timeframes={"entry": "5m"},
        entry_conditions=[Condition(type="indicator_compare", indicator="rsi", op="<", value=30)],
        exit_conditions=[Condition(type="indicator_compare", indicator="macd", op=">", value=0)],
        concepts_used=["resistance"],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0),
        take_profit=SLTPSpec(type="rr", value=2.5),
        risk_pct=1.0, risk_reward=2.5,
    )
    base.update(overrides)
    return StrategyConfig(**base)


def _close_a_trade(strategy_id, strategy_name, pnl, is_win, rr=None):
    now = datetime.now(timezone.utc).isoformat()
    with storage.get_conn() as conn:
        conn.execute(
            """INSERT INTO paper_positions
               (id, exchange, symbol, direction, entry_price, exit_price, size,
                entry_time, exit_time, pnl, status, strategy_id, strategy_name,
                created_at, closed_at)
               VALUES (?, 'binance', 'BTCUSDT', 'long', 100, 105, 1, 0, 1, ?, 'closed', ?, ?, ?, ?)""",
            (f"{strategy_id}-{pnl}", pnl, strategy_id, strategy_name, now, now),
        )
    storage.update_paper_strategy_performance(strategy_id, strategy_name, pnl, is_win, rr, now)


def test_strategy_with_zero_trades_shows_real_zeros_not_placeholders(test_db):
    sid = lib.create(_make_strategy(name="Brand New Strategy"))
    result = pt_api.get_strategy_overview()
    row = next(r for r in result["strategies"] if r["strategy_id"] == sid)
    assert row["win_rate"] == 0.0
    assert row["closed_trades"] == 0
    assert row["total_pnl"] == 0.0
    assert row["in_paper_trading"] is False


def test_strategy_with_no_local_backtest_shows_no_backtest_block(test_db):
    """Master Task 3, Phase 0.7: the dual-row Strategies table's top
    (Backtest) row must be honestly absent, not a fabricated 0/placeholder,
    for a strategy that has never completed a local backtest batch."""
    sid = lib.create(_make_strategy(name="Never Backtested"))
    row = next(r for r in pt_api.get_strategy_overview()["strategies"] if r["strategy_id"] == sid)
    assert row["backtest"] is None


def test_strategy_overview_surfaces_a_saved_backtest_snapshot(test_db):
    """The other half of the dual-row wiring: once
    strategy_library.save_backtest_snapshot has written a snapshot (done by
    sindhu_web/api/backtesting.py's _compute_strategies_list on the local
    machine), this cloud-reachable endpoint must surface it unchanged --
    this is the exact channel that lets a cloud deploy (no backtest_*
    tables of its own) show real backtest numbers at all."""
    sid = lib.create(_make_strategy(name="Backtested Strategy"))
    snapshot = {
        "win_rate": 62.5, "profit_factor": 1.85, "total_trades": 140,
        "batch_id": "batch123", "computed_at": "2026-01-01T00:00:00+00:00",
    }
    lib.save_backtest_snapshot(sid, snapshot)

    row = next(r for r in pt_api.get_strategy_overview()["strategies"] if r["strategy_id"] == sid)
    assert row["backtest"] == snapshot


def test_save_backtest_snapshot_skips_the_write_when_unchanged(test_db, monkeypatch):
    sid = lib.create(_make_strategy(name="Unchanged Snapshot"))
    snapshot = {"win_rate": 50.0, "profit_factor": 1.1, "total_trades": 30, "batch_id": "b1", "computed_at": "2026-01-01T00:00:00+00:00"}
    lib.save_backtest_snapshot(sid, snapshot)

    write_calls = []
    monkeypatch.setattr(lib, "_write_meta", lambda strategy_id, meta: write_calls.append(meta))
    lib.save_backtest_snapshot(sid, snapshot)  # identical snapshot -- must not write again
    assert write_calls == []

    lib.save_backtest_snapshot(sid, {**snapshot, "win_rate": 51.0})  # genuinely changed -- must write
    assert len(write_calls) == 1


def test_fixed_rr_strategy_shows_its_configured_ratio_not_an_average(test_db):
    """take_profit.type == 'rr' means this strategy always targets the same
    multiple -- the table must show that fixed number (2.5), not whatever
    average has accumulated from trades so far."""
    sid = lib.create(_make_strategy(name="Fixed RR Strategy"))
    _close_a_trade(sid, "Fixed RR Strategy", pnl=50.0, is_win=True, rr=4.0)
    result = pt_api.get_strategy_overview()
    row = next(r for r in result["strategies"] if r["strategy_id"] == sid)
    assert row["risk_reward"] == 2.5
    assert row["risk_reward_is_fixed"] is True


def test_structure_based_strategy_falls_back_to_average_live_rr(test_db):
    """No fixed ratio to state (structure-based SL/TP) -- must show the
    average R:R actually realized across live paper trades instead."""
    sid = lib.create(_make_strategy(
        name="Structure Based Strategy",
        take_profit=SLTPSpec(type="structure"),
        risk_reward=None,
    ))
    _close_a_trade(sid, "Structure Based Strategy", pnl=30.0, is_win=True, rr=3.0)
    _close_a_trade(sid, "Structure Based Strategy", pnl=-10.0, is_win=False, rr=1.0)
    result = pt_api.get_strategy_overview()
    row = next(r for r in result["strategies"] if r["strategy_id"] == sid)
    assert row["risk_reward"] == 2.0  # average of 3.0 and 1.0
    assert row["risk_reward_is_fixed"] is False


def test_structure_based_strategy_with_no_trades_yet_has_no_rr_to_show(test_db):
    sid = lib.create(_make_strategy(
        name="Untested Structure Strategy",
        take_profit=SLTPSpec(type="structure"),
        risk_reward=None,
    ))
    result = pt_api.get_strategy_overview()
    row = next(r for r in result["strategies"] if r["strategy_id"] == sid)
    assert row["risk_reward"] is None
    assert row["risk_reward_is_fixed"] is False


def test_active_strategy_is_flagged_in_paper_trading(test_db):
    sid = lib.create(_make_strategy(name="Active Strategy"))
    storage.save_paper_strategy_config(sid, True, 5, [], [], datetime.now(timezone.utc).isoformat())
    result = pt_api.get_strategy_overview()
    row = next(r for r in result["strategies"] if r["strategy_id"] == sid)
    assert row["in_paper_trading"] is True


def test_a_valid_strategy_can_be_activated(test_db):
    sid = lib.create(_make_strategy(name="Good Strategy"))
    result = pt_api.get_strategy_overview()
    row = next(r for r in result["strategies"] if r["strategy_id"] == sid)
    assert row["can_activate"] is True
    assert row["activation_blocked_reason"] is None


def test_a_strategy_missing_an_entry_timeframe_is_blocked_from_activation(test_db):
    """validator.validate() requires an 'entry' timeframe -- a strategy
    missing one must be blocked here exactly like /readiness/{id} already
    blocks it, with the reason surfaced for the CEO to read."""
    sid = lib.create(_make_strategy(name="Broken Strategy", timeframes={}))
    result = pt_api.get_strategy_overview()
    row = next(r for r in result["strategies"] if r["strategy_id"] == sid)
    assert row["can_activate"] is False
    assert row["activation_blocked_reason"]
    assert "timeframe" in row["activation_blocked_reason"].lower()


def test_paper_config_is_preserved_for_the_activation_call(test_db):
    """The frontend's Move-to-Paper-Trading action must be able to
    re-submit the strategy's EXISTING priority/coins/market-types alongside
    enabled:true, so activating a strategy can never silently wipe a
    previously-set priority or coin restriction."""
    sid = lib.create(_make_strategy(name="Configured Strategy"))
    storage.save_paper_strategy_config(sid, False, 8, ["BTCUSDT", "ETHUSDT"], ["spot"],
                                        datetime.now(timezone.utc).isoformat())
    result = pt_api.get_strategy_overview()
    row = next(r for r in result["strategies"] if r["strategy_id"] == sid)
    assert row["paper_config"]["priority"] == 8
    assert row["paper_config"]["supported_coins"] == ["BTCUSDT", "ETHUSDT"]
    assert row["paper_config"]["supported_market_types"] == ["spot"]
