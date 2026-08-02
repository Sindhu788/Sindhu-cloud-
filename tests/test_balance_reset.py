"""Batch 4, Task 2 -- the Reset Balance button (Paper Trading). Resets
ONLY the working balance (realized_pnl_total per strategy book) back to
the configured initial_balance; closed trade history, lessons, evolution
data, strategy performance stats, and win/trade counters must survive
completely intact. Open positions are left running, never force-closed --
see storage.reset_paper_balance's docstring for why that's safe (they
don't factor into the balance figure until they close).
"""

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from data_engine import config as base_config, storage
from paper_trading import config as pt_config
from sindhu_web.api import paper_trading as pt_api


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _close_a_trade(strategy_id, pnl, pos_id="p1"):
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    storage.open_paper_position({
        "id": pos_id, "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0, "entry_time": now_ms,
        "created_at": _now_iso(), "strategy_id": strategy_id, "strategy_name": "Test Strategy",
    })
    storage.close_paper_position(
        pos_id, exit_price=100.0 + pnl, exit_time=now_ms, pnl=pnl, pnl_pct=pnl,
        exit_reason="take_profit", lifecycle={}, reflection={}, closed_at=_now_iso(),
        book_key=strategy_id,
    )


def test_reset_zeroes_realized_pnl_but_keeps_closed_count_and_win_count(test_db):
    _close_a_trade("strat1", pnl=50.0, pos_id="p1")
    before = storage.list_paper_account_states()[0]
    assert before["realized_pnl_total"] == 50.0
    assert before["closed_count"] == 1
    assert before["win_count"] == 1

    storage.reset_paper_balance(_now_iso())

    after = storage.list_paper_account_states()[0]
    assert after["realized_pnl_total"] == 0.0
    assert after["closed_count"] == 1  # trade count survives -- not deleted
    assert after["win_count"] == 1  # win-rate stat survives -- not deleted


def test_reset_never_touches_the_actual_trade_history_row(test_db):
    _close_a_trade("strat1", pnl=50.0, pos_id="p1")
    storage.reset_paper_balance(_now_iso())
    trades = storage.list_paper_closed_trades_ordered(strategy_id="strat1", limit=10)
    assert len(trades) == 1
    assert trades[0]["pnl"] == 50.0  # the historical trade record itself is untouched


def test_reset_never_touches_lessons_or_strategy_performance(test_db):
    storage.save_lesson({
        "id": "lesson1", "title": "Test Lesson", "category": "risk", "description": "d",
        "priority": "Medium", "status": "active", "notes": None,
        "apply_backtesting": True, "apply_paper_trading": True, "apply_evolution": True,
        "rule_type": "require_if_true", "direction": None, "conditions": [],
        "created_at": _now_iso(), "updated_at": _now_iso(), "version": 1,
        "tags": [], "supported_market_types": [], "supported_timeframes": [],
    })
    with storage.get_conn() as conn:
        conn.execute(
            "INSERT INTO paper_strategy_performance (strategy_id, strategy_name, trades, wins, losses, total_pnl) "
            "VALUES ('strat1', 'Test Strategy', 10, 6, 4, 123.45)"
        )
    storage.reset_paper_balance(_now_iso())

    assert len(storage.list_lessons()) == 1
    with storage.get_conn() as conn:
        row = conn.execute(
            "SELECT trades, wins, losses, total_pnl FROM paper_strategy_performance WHERE strategy_id='strat1'"
        ).fetchone()
    assert row == (10, 6, 4, 123.45)


def test_reset_leaves_open_positions_running_not_closed(test_db):
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    storage.open_paper_position({
        "id": "open1", "exchange": "binance", "symbol": "ETHUSDT", "direction": "long",
        "entry_price": 50.0, "size": 1.0, "risk_amount": 5.0, "entry_time": now_ms,
        "created_at": _now_iso(), "strategy_id": "strat1", "strategy_name": "Test Strategy",
    })
    summary = storage.reset_paper_balance(_now_iso())
    assert summary["open_positions_left_running"] == 1

    open_positions = storage.get_open_paper_positions()
    assert len(open_positions) == 1
    assert open_positions[0]["id"] == "open1"  # still open, not administratively closed


def test_reset_returns_a_correct_summary(test_db):
    _close_a_trade("strat1", pnl=50.0, pos_id="p1")
    _close_a_trade("strat2", pnl=-20.0, pos_id="p2")
    summary = storage.reset_paper_balance(_now_iso())
    assert summary["strategies_reset"] == 2
    assert summary["previous_total_realized_pnl"] == 30.0


def test_combined_balance_returns_to_starting_amount_after_reset(test_db):
    pt_config.save({"initial_balance": 10000.0})
    _close_a_trade("strat1", pnl=500.0, pos_id="p1")

    before = pt_api.get_status()
    assert before["balance"] == 10500.0

    storage.reset_paper_balance(_now_iso())

    after = pt_api.get_status()
    assert after["balance"] == 10000.0


def test_endpoint_requires_explicit_confirmation(test_db):
    with pytest.raises(HTTPException) as exc_info:
        pt_api.reset_balance(pt_api.ResetBalanceRequest(confirm=False))
    assert exc_info.value.status_code == 400


def test_endpoint_resets_when_confirmed(test_db):
    _close_a_trade("strat1", pnl=50.0, pos_id="p1")
    result = pt_api.reset_balance(pt_api.ResetBalanceRequest(confirm=True))
    assert result["ok"] is True
    assert result["strategies_reset"] == 1
    assert storage.list_paper_account_states()[0]["realized_pnl_total"] == 0.0


def test_preview_shows_real_numbers_before_reset(test_db):
    pt_config.save({"initial_balance": 10000.0})
    _close_a_trade("strat1", pnl=100.0, pos_id="p1")
    preview = pt_api.preview_reset_balance()
    assert preview["current_combined_balance"] == 10100.0
    assert preview["reset_combined_balance"] == 10000.0
    assert preview["closed_trades_preserved"] == 1


def test_balance_history_graph_starts_fresh_after_a_reset(test_db):
    _close_a_trade("strat1", pnl=500.0, pos_id="p1")
    reset_at = _now_iso()
    storage.reset_paper_balance(reset_at)
    _close_a_trade("strat1", pnl=25.0, pos_id="p2")

    result = pt_api.get_balance_history("strat1")
    # Only the post-reset trade shows up in the walked-forward points --
    # the pre-reset $500 trade stays in the database (see the trade
    # history test above) but no longer skews the live balance graph.
    assert len(result["points"]) == 2  # base point + the one post-reset trade
    assert result["points"][-1]["balance"] == result["initial_balance"] + 25.0
