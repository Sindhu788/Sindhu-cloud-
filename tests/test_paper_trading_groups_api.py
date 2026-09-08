"""API endpoints for CEO Task 3 (Independent Paper Trading Groups):
GET /api/paper-trading/groups, GET /api/paper-trading/groups/{key},
POST /api/paper-trading/groups/sync, POST /api/paper-trading/groups/{id}/move.
Calls the endpoint functions directly, same convention as
test_strategy_overview.py.
"""
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from data_engine import storage
from paper_trading import strategy_groups
from sindhu_web.api import paper_trading as pt_api


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _enable_and_close(strategy_id, pnl):
    storage.save_paper_strategy_config(strategy_id, True, 5, [], [], _now_iso())
    now = _now_iso()
    with storage.get_conn() as conn:
        conn.execute(
            """INSERT INTO paper_positions
               (id, exchange, symbol, direction, entry_price, size, entry_time,
                pnl, status, strategy_id, strategy_name, created_at, closed_at)
               VALUES (?, 'binance', 'BTCUSDT', 'long', 100, 1, 0, ?, 'closed', ?, ?, ?, ?)""",
            (f"{strategy_id}-{pnl}", pnl, strategy_id, strategy_id, now, now),
        )
        conn.execute(
            """INSERT INTO paper_account_state (strategy_id, realized_pnl_total, closed_count, win_count, updated_at)
               VALUES (?, ?, 1, ?, ?)""",
            (strategy_id, pnl, 1 if pnl > 0 else 0, now),
        )


def test_get_groups_returns_all_three_independently(test_db, monkeypatch):
    monkeypatch.setattr(strategy_groups, "CHALLENGE_SIZE", 0)
    _enable_and_close("loser1", -30)
    _enable_and_close("winner1", 50)

    result = pt_api.get_paper_trading_groups()

    assert set(result["groups"].keys()) == {"losing", "profitable", "challenge"}
    assert "challenge_daily" in result
    assert "challenge_recent_days" in result
    assert result["groups"]["losing"]["total_pnl"] == -30


def test_get_one_group_endpoint(test_db, monkeypatch):
    monkeypatch.setattr(strategy_groups, "CHALLENGE_SIZE", 0)
    _enable_and_close("loser1", -30)
    strategy_groups.sync_group_assignments()

    result = pt_api.get_one_paper_trading_group("losing")
    assert result["group_key"] == "losing"
    assert result["total_pnl"] == -30


def test_get_unknown_group_404s(test_db):
    with pytest.raises(HTTPException) as exc_info:
        pt_api.get_one_paper_trading_group("nonexistent")
    assert exc_info.value.status_code == 404


def test_manual_move_overrides_and_sticks(test_db, monkeypatch):
    monkeypatch.setattr(strategy_groups, "CHALLENGE_SIZE", 0)
    _enable_and_close("s1", 10)
    strategy_groups.sync_group_assignments()
    assert storage.list_paper_strategy_groups()["s1"] == "profitable"

    body = pt_api.MoveStrategyGroupRequest(group_key="losing")
    result = pt_api.move_strategy_group("s1", body)
    assert result["ok"] is True
    assert storage.list_paper_strategy_groups()["s1"] == "losing"

    # A later sync must not undo the manual override.
    strategy_groups.sync_group_assignments()
    assert storage.list_paper_strategy_groups()["s1"] == "losing"


def test_manual_move_rejects_unknown_group(test_db):
    body = pt_api.MoveStrategyGroupRequest(group_key="bogus")
    with pytest.raises(HTTPException) as exc_info:
        pt_api.move_strategy_group("s1", body)
    assert exc_info.value.status_code == 400


def test_sync_endpoint_is_idempotent(test_db):
    _enable_and_close("s1", 10)
    first = pt_api.sync_paper_trading_groups()
    assert first["first_run"] is True

    second = pt_api.sync_paper_trading_groups()
    assert second["first_run"] is False
    assert second["assigned"] == {"losing": [], "profitable": [], "challenge": []}
