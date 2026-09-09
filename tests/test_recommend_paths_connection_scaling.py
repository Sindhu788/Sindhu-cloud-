"""Urgent bug fix, 2026-09-09: challenge_analysis.recommend_paths() --
used by /api/paper-trading/challenges (setup) and .../full-analysis --
called _closed_rows(strategy_id, symbol) TWICE per real strategy+coin
combination (once directly, once again inside consistency_check()), each
its own fresh Postgres connection. With 75 strategies enabled and trading
across several coins each, hundreds of real combinations meant hundreds
of connections for one request. Fixed by fetching every closed row ONCE
and grouping in memory, reused by both call sites.
"""
from datetime import datetime, timedelta, timezone

import pytest

from data_engine import config as base_config, storage
from paper_trading import challenge_analysis


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _iso(days_ago):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _trade(pid, strategy_id, symbol, pnl, risk_amount=5.0, closed_days_ago=0):
    storage.open_paper_position({
        "id": pid, "exchange": "binance", "symbol": symbol, "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": risk_amount,
        "entry_time": 1700000000000, "created_at": _iso(closed_days_ago),
        "strategy_id": strategy_id, "strategy_name": strategy_id,
    })
    storage.close_paper_position(
        pid, 100.0, 1700000000000 + 30 * 60000, pnl, pnl, "take_profit", {}, {}, _iso(closed_days_ago),
    )


def _counting_get_conn(monkeypatch):
    call_count = {"n": 0}
    real_get_conn = storage.get_conn

    def counting():
        call_count["n"] += 1
        return real_get_conn()

    monkeypatch.setattr(storage, "get_conn", counting)
    return call_count


def test_recommend_paths_stays_low_on_connections_at_scale(test_db, monkeypatch):
    # 20 strategies x 3 coins each x a few trades = 60 real combinations,
    # comfortably standing in for "75 strategies trading several coins
    # each" without making the test itself slow.
    n = 0
    for s in range(20):
        for c in range(3):
            symbol = f"COIN{c}USDT"
            for t in range(3):
                _trade(f"p{n}", f"strat{s}", symbol, pnl=10.0 if t % 2 else -3.0, closed_days_ago=t)
                n += 1

    call_count = _counting_get_conn(monkeypatch)
    result = challenge_analysis.recommend_paths(start_amount=100.0, target_amount=110.0, days=30)

    assert len(result["paths"]) > 0
    # Before this fix: 2 connections per combination (60 combos -> 120+).
    # Now: a small constant regardless of how many real combinations exist.
    assert call_count["n"] < 6


def test_recommend_paths_results_unchanged_by_the_batching(test_db):
    for s in range(3):
        for t in range(30):
            _trade(f"p{s}_{t}", f"strat{s}", "BTCUSDT", pnl=10.0 if t % 3 else -4.0, closed_days_ago=t)

    result = challenge_analysis.recommend_paths(start_amount=100.0, target_amount=110.0, days=30)
    assert len(result["paths"]) == 3
    for path in result["paths"]:
        assert path["sample_size"] == 30
        assert "consistency" in path
