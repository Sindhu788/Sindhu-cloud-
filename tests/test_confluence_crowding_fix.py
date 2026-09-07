"""Master Task 6, item 1.1 -- regression test for the coin-crowding bug.

Before the fix: confluence.py's crowding factor counted ANY open position
on a symbol (including the SAME strategy's own existing position) as
"crowding", so a strategy that already had one open trade on a coin was
marked as crowding ITSELF -- permanently capping its own confluence score
on every future signal for that same coin until the position closed.

After the fix: only an OTHER strategy's open position on the same coin
counts as crowding; a strategy's own existing position never counts
against its own new signal.
"""

from paper_trading import confluence


def _position(id, strategy_id, symbol="BTCUSDT", exchange="binance", direction="long"):
    return {
        "id": id, "strategy_id": strategy_id, "strategy_name": strategy_id,
        "symbol": symbol, "direction": direction, "entry_price": 100.0,
        "stop_loss": 95.0, "take_profit": 110.0, "market_state": "trending_up",
        "session": "london", "entry_reason": "test", "exchange": exchange,
        "size": 1.0, "risk_amount": 5.0,
        "entry_time": 0, "created_at": "2026-01-01T00:00:00+00:00",
    }


def _crowding_result(factors):
    return next(f for f in factors if "crowding" in f["name"].lower())


def test_own_existing_position_no_longer_counts_as_crowding(test_db):
    """The bug scenario: strategy A already has an open BTCUSDT position.
    Strategy A gets a brand-new BTCUSDT signal. Before the fix, this factor
    was reported as FAILED (crowded) purely because of A's own position --
    after the fix it must PASS, since no OTHER strategy is involved."""
    import data_engine.storage as storage
    storage.open_paper_position(_position("pos1", "strat_A"))

    result = confluence.score_confluence(
        "strat_A", "BTCUSDT", "binance", "trending_up", "london", "bullish",
    )
    crowding = _crowding_result(result["factors"])
    assert crowding["result"] is True, (
        "REGRESSION: strategy's own open position on the same coin is being "
        "counted as crowding against itself"
    )


def test_a_different_strategys_position_still_counts_as_real_crowding(test_db):
    """The fix must not go too far the other way: if a DIFFERENT strategy
    has an open position on the same coin, that is genuine cross-strategy
    concentration risk and must still be flagged."""
    import data_engine.storage as storage
    storage.open_paper_position(_position("pos1", "strat_A"))
    storage.open_paper_position(_position("pos2", "strat_B"))

    result = confluence.score_confluence(
        "strat_A", "BTCUSDT", "binance", "trending_up", "london", "bullish",
    )
    crowding = _crowding_result(result["factors"])
    assert crowding["result"] is False, (
        "A different strategy's open position on the same coin should still "
        "be flagged as crowding"
    )


