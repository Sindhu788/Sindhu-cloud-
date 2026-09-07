"""Master Task 6, item 1.2 -- Wilson Gate Broadening regression test.

Before the fix: telegram_bot._pattern_reliability_for() matched on the
exact (strategy, coin, market_state, session) combination, so a strategy's
trades on one coin spread across different market conditions/sessions were
never combined -- each condition-specific slice had to independently reach
the 25-trade minimum, which almost never happened even for an
otherwise-active strategy+coin pair.

After the fix: it aggregates at the (strategy, coin) level -- trades from
every market_state/session on that coin count together, while the 25-trade
statistical minimum itself is unchanged.
"""

from data_engine import storage
from paper_trading import telegram_bot


def _closed_trade(id, strategy_id, symbol, market_state, session, pnl):
    return {
        "id": id, "strategy_id": strategy_id, "strategy_name": strategy_id,
        "symbol": symbol, "direction": "long", "entry_price": 100.0,
        "stop_loss": 95.0, "take_profit": 110.0, "market_state": market_state,
        "session": session, "entry_reason": "test", "exchange": "binance",
        "size": 1.0, "risk_amount": 5.0, "entry_time": 0,
        "created_at": "2026-01-01T00:00:00+00:00",
    }


def _seed_scattered_trades(strategy_id, symbol, total, wins):
    """Spreads `total` closed trades for one (strategy, symbol) pair across
    4 different market_state/session combinations -- exactly the
    fragmentation pattern the bug produced -- so no single old-style narrow
    group ever reaches `total` trades even though the pair genuinely has
    that many combined."""
    conditions = [
        ("trending_up", "london"), ("trending_down", "ny"),
        ("ranging", "asian"), ("breakout", "ny"),
    ]
    for i in range(total):
        market_state, session = conditions[i % len(conditions)]
        pnl = 1.0 if i < wins else -1.0
        pos = _closed_trade(f"pos{i}", strategy_id, symbol, market_state, session, pnl)
        storage.open_paper_position(pos)
        storage.close_paper_position(
            pos["id"], 101.0 if i < wins else 99.0, 0, pnl, pnl, "take_profit", {}, {},
            "2026-01-02T00:00:00+00:00", book_key=strategy_id,
        )


def test_scattered_trades_never_reach_25_under_the_old_narrow_grouping(test_db):
    """Confirms the fragmentation problem is real: 28 trades split across 4
    conditions means every OLD narrow (strategy, coin, condition) group
    tops out at 7 -- never close to the 25-trade minimum."""
    _seed_scattered_trades("strat_broad", "ETHUSDT", total=28, wins=20)
    patterns = storage.list_paper_coin_pattern_memory(strategy_id="strat_broad")
    assert all(p["trades"] < 25 for p in patterns), (
        "test setup invariant broken: expected every narrow group to stay under 25"
    )
    assert max(p["trades"] for p in patterns) <= 7


def test_broadened_strategy_coin_aggregation_reaches_the_25_trade_gate(test_db):
    """The same 28 scattered trades, aggregated at (strategy, coin) level,
    must now clear the 25-trade Wilson gate and be classified reliable."""
    _seed_scattered_trades("strat_broad", "ETHUSDT", total=28, wins=20)
    stats = storage.get_paper_strategy_coin_reliability_stats("strat_broad", "ETHUSDT")
    assert stats["trades"] == 28
    assert stats["wins"] == 20

    result = telegram_bot._pattern_reliability_for("strat_broad", "ETHUSDT", "trending_up", "london")
    assert result["reliable"] is True
    assert result["sample_size"] == 28


def test_25_trade_minimum_itself_is_unchanged_not_lowered(test_db):
    """24 combined trades (still scattered) must still be reported as
    insufficient data -- broadening groups is not the same as lowering the
    statistical bar."""
    _seed_scattered_trades("strat_thin", "SOLUSDT", total=24, wins=20)
    result = telegram_bot._pattern_reliability_for("strat_thin", "SOLUSDT", "trending_up", "london")
    assert result["reliable"] is False
    assert result["status"] == "insufficient_data"
