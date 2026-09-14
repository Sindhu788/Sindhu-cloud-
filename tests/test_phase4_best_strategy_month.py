"""Grand Master Batch, Phase 4 Item 13 -- Best Strategy This Month."""

from datetime import datetime, timedelta, timezone

from data_engine import storage
from paper_trading import best_strategy_highlight


def _close(pos_id, strategy_id, pnl, closed_at):
    storage.open_paper_position({
        "id": pos_id, "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": int(datetime.now(timezone.utc).timestamp() * 1000),
        "created_at": closed_at, "strategy_id": strategy_id, "strategy_name": strategy_id,
    })
    storage.close_paper_position(pos_id, 100.0 + pnl, closed_at, pnl, pnl, "take_profit", {}, {}, closed_at)


def test_no_closed_trades_this_month_returns_none(test_db):
    assert best_strategy_highlight.best_strategy_this_month() is None


def test_picks_highest_total_pnl_strategy(test_db):
    now = datetime.now(timezone.utc)
    this_month = now.replace(day=min(now.day, 28)).isoformat()
    _close("p1", "strat_good", 50.0, this_month)
    _close("p2", "strat_good", 20.0, this_month)
    _close("p3", "strat_bad", 60.0, this_month)
    _close("p4", "strat_bad", -100.0, this_month)
    result = best_strategy_highlight.best_strategy_this_month(now=now)
    assert result["strategy_id"] == "strat_good"
    assert result["total_pnl"] == 70.0
    assert result["closed_trades"] == 2
    assert result["win_rate_pct"] == 100.0


def test_ignores_trades_closed_before_this_month(test_db):
    now = datetime.now(timezone.utc)
    last_month = (now.replace(day=1) - timedelta(days=5)).isoformat()
    _close("p1", "strat_old", 500.0, last_month)
    result = best_strategy_highlight.best_strategy_this_month(now=now)
    assert result is None


def test_win_rate_reflects_mixed_results(test_db):
    now = datetime.now(timezone.utc)
    this_month = now.replace(day=min(now.day, 28)).isoformat()
    _close("p1", "strat1", 10.0, this_month)
    _close("p2", "strat1", -5.0, this_month)
    _close("p3", "strat1", 10.0, this_month)
    result = best_strategy_highlight.best_strategy_this_month(now=now)
    assert result["closed_trades"] == 3
    assert round(result["win_rate_pct"], 1) == 66.7
