"""Batch 2, Task 1 -- the Overview page's "Top Strategies by Profit" and
the Reports page's "Best Strategy" label both come from
/api/reports/best-worst/strategies. Real bug: it used to average
avg_profit_pct across EVERY completed batch ever run for a strategy,
including ancient ones from before long-fixed engine bugs -- one real
stored batch had avg_profit_pct = 425,679,667,191.65% (a since-fixed
runaway-compounding bug), which permanently poisoned the displayed number
even though the strategy's real, current backtests show a small loss.
Fixed to rank by each strategy's MOST RECENT completed batch only.
"""

from datetime import datetime, timedelta, timezone

from data_engine import storage
from sindhu_web.api.reports import best_worst_strategies


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _make_batch(batch_id, strategy_name, created_at, symbol_results):
    """symbol_results: list of (symbol, total_trades, wins, profit_pct, final_balance, max_dd)."""
    storage.create_batch(batch_id, strategy_name, "binance", {"initial_balance": 1000.0}, created_at)
    for symbol, trades, wins, profit_pct, final_balance, max_dd in symbol_results:
        storage.save_result(batch_id, symbol, "1m", "completed", {
            "total_trades": trades, "wins": wins, "profit_pct": profit_pct,
            "final_balance": final_balance, "max_drawdown_pct": max_dd,
        }, created_at)
    storage.update_batch_status(batch_id, "completed", created_at)


def test_ranking_uses_latest_batch_not_an_all_time_average(test_db):
    """The exact real-world scenario: an ancient batch with an insane,
    since-fixed profit_pct must NOT drag the strategy's displayed ranking
    away from its real, current backtest result."""
    old_time = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
    recent_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

    # Ancient batch, run under a long-fixed engine bug -- absurd profit_pct.
    _make_batch("old_batch_1", "Daily High-Low Liquidity Strategy", old_time, [
        ("ZECUSDT", 5145, 4537, 8256789696225.39, 82567896963253.94, 23.19),
    ])
    # Current, real batch -- small real loss, matches Backtest History.
    _make_batch("new_batch_1", "Daily High-Low Liquidity Strategy", recent_time, [
        ("AAVEUSDT", 792, 21, -2.96, 970.4, 75.72),
    ])

    result = best_worst_strategies()
    row = next(r for r in result["ranking"] if r["strategy"] == "Daily High-Low Liquidity Strategy")
    assert row["avg_profit_pct"] == -2.96
    assert row["batch_id"] == "new_batch_1"
    # The old bug: 27 billion+ % or similar magnitude. Confirm the fix
    # never even gets close to that regardless of the ancient batch.
    assert abs(row["avg_profit_pct"]) < 1000


def test_batches_count_reflects_all_completed_batches_even_though_ranking_uses_latest(test_db):
    t1 = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    t2 = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    _make_batch("b1", "Strategy X", t1, [("BTCUSDT", 10, 5, 3.0, 1030.0, 5.0)])
    _make_batch("b2", "Strategy X", t2, [("BTCUSDT", 12, 7, 5.0, 1050.0, 4.0)])

    result = best_worst_strategies()
    row = next(r for r in result["ranking"] if r["strategy"] == "Strategy X")
    assert row["avg_profit_pct"] == 5.0  # from the latest batch (b2) only
    assert row["batches"] == 2           # but the count still reflects both


def test_best_and_worst_strategy_labels_use_real_current_numbers(test_db):
    t = _now_iso()
    _make_batch("good_batch", "Good Strategy", t, [("BTCUSDT", 20, 15, 12.0, 1120.0, 3.0)])
    _make_batch("bad_batch", "Bad Strategy", t, [("BTCUSDT", 20, 2, -50.0, 500.0, 50.0)])

    result = best_worst_strategies()
    assert result["best_strategy"] == "Good Strategy"
    assert result["worst_strategy"] == "Bad Strategy"


def test_no_completed_batches_returns_empty_ranking(test_db):
    result = best_worst_strategies()
    assert result["ranking"] == []
    assert result["best_strategy"] is None
    assert result["worst_strategy"] is None
