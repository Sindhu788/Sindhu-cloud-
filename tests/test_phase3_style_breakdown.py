"""5-Phase Improvement Batch, Phase 3.5 -- Strategies-by-Trading-Style
breakdown (paper_trading/strategy_groups.style_breakdown). Reuses
summarize_strategy_ids (the same math group_summary uses) and
telegram_bot.trading_style_for_timeframe (Phase 2.4) -- no new analytics.
"""
from datetime import datetime, timezone

from data_engine import storage
from paper_trading import strategy_groups


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _enable_strategy(strategy_id, now_iso=None):
    storage.save_paper_strategy_config(strategy_id, True, 5, [], [], now_iso or _now_iso())


def _close_trade(strategy_id, pnl, timeframe, closed_at=None):
    closed_at = closed_at or _now_iso()
    with storage.get_conn() as conn:
        conn.execute(
            """INSERT INTO paper_positions
               (id, exchange, symbol, direction, entry_price, size, entry_time,
                pnl, status, strategy_id, strategy_name, created_at, closed_at, timeframe)
               VALUES (?, 'binance', 'BTCUSDT', 'long', 100, 1, 0, ?, 'closed', ?, ?, ?, ?, ?)""",
            (f"{strategy_id}-{closed_at}-{pnl}", pnl, strategy_id, strategy_id, closed_at, closed_at, timeframe),
        )
        conn.execute(
            """INSERT INTO paper_account_state (strategy_id, realized_pnl_total, closed_count, win_count, updated_at)
               VALUES (?, ?, 1, ?, ?)
               ON CONFLICT(strategy_id) DO UPDATE SET
                 realized_pnl_total = realized_pnl_total + excluded.realized_pnl_total,
                 closed_count = closed_count + 1,
                 win_count = win_count + excluded.win_count,
                 updated_at = excluded.updated_at""",
            (strategy_id, pnl, 1 if pnl > 0 else 0, closed_at),
        )


def test_primary_timeframe_picks_the_most_traded_one(test_db):
    _enable_strategy("scalper1")
    _close_trade("scalper1", 5, "5m")
    _close_trade("scalper1", 3, "5m")
    _close_trade("scalper1", -1, "1h")  # minority timeframe -- should lose the mode

    result = storage.get_primary_timeframe_by_strategy()
    assert result["scalper1"] == "5m"


def test_style_breakdown_buckets_strategies_correctly(test_db):
    _enable_strategy("scalper1")
    _close_trade("scalper1", 10, "5m")
    _enable_strategy("swinger1")
    _close_trade("swinger1", -20, "1d")
    _enable_strategy("intraday1")
    _close_trade("intraday1", 15, "1h")

    result = strategy_groups.style_breakdown()

    assert result["scalping"]["strategy_count"] == 1
    assert result["scalping"]["total_pnl"] == 10
    assert result["swing"]["strategy_count"] == 1
    assert result["swing"]["total_pnl"] == -20
    assert result["intraday"]["strategy_count"] == 1
    assert result["intraday"]["total_pnl"] == 15


def test_style_breakdown_puts_no_data_strategies_in_undetermined(test_db):
    _enable_strategy("brand_new_strategy")  # enabled, but has never traded

    result = strategy_groups.style_breakdown()

    undetermined_ids = [s["strategy_id"] for s in result["undetermined"]["strategies"]]
    assert "brand_new_strategy" in undetermined_ids


def test_style_breakdown_total_strategy_count_matches_universe(test_db):
    _enable_strategy("scalper1")
    _close_trade("scalper1", 10, "5m")
    _enable_strategy("swinger1")
    _close_trade("swinger1", -20, "1d")
    _enable_strategy("no_data_yet")

    result = strategy_groups.style_breakdown()
    total = sum(bucket["strategy_count"] for bucket in result.values())
    assert total == 3  # every enabled strategy appears in exactly one bucket


def test_summarize_strategy_ids_matches_group_summary_math(test_db):
    _enable_strategy("stratA")
    _close_trade("stratA", 25, "1h")
    strategy_groups.sync_group_assignments()

    direct = strategy_groups.summarize_strategy_ids(["stratA"])
    via_group = strategy_groups.group_summary(strategy_groups.get_group("stratA"))

    assert direct["total_pnl"] == 25
    assert via_group["total_pnl"] == 25
