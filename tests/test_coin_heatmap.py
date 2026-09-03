"""Grand Feature Expansion, Phase 3 Feature 3: Coin-Performance Heatmap
(paper_trading.coin_heatmap.compute_coin_heatmap) -- which coins are
CONSISTENTLY profitable across every strategy that traded them, distinct
from storage.list_paper_coin_stats' plain aggregate ranking (which a
single outlier strategy could secretly be propping up).
"""

from data_engine import storage
from paper_trading import coin_heatmap


def _close(position_id, symbol, pnl, strategy_id):
    pos = {
        "id": position_id, "exchange": "binance", "symbol": symbol, "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": 1700000000000, "created_at": "2026-01-01T00:00:00+00:00",
        "strategy_id": strategy_id, "strategy_name": strategy_id,
    }
    storage.open_paper_position(pos)
    storage.close_paper_position(position_id, 100.0 + pnl, 1700000100000, pnl, pnl,
                                  "take_profit" if pnl >= 0 else "stop_loss", {}, {}, "2026-01-02T00:00:00+00:00")


def test_a_coin_profitable_across_every_strategy_scores_100pct_consistency(test_db):
    _close("p1", "BTCUSDT", 10.0, "strat1")
    _close("p2", "BTCUSDT", 20.0, "strat2")
    _close("p3", "BTCUSDT", 5.0, "strat3")

    result = coin_heatmap.compute_coin_heatmap()
    row = next(r for r in result if r["symbol"] == "BTCUSDT")
    assert row["strategy_count"] == 3
    assert row["profitable_strategy_count"] == 3
    assert row["consistency_pct"] == 100.0


def test_a_coin_propped_up_by_one_outlier_strategy_is_flagged_inconsistent(test_db):
    """The whole point of this feature: a coin can have a big positive
    total PnL while being reliably BAD for most strategies that traded
    it -- consistency must reflect that, not just the raw total."""
    _close("p1", "ETHUSDT", 1000.0, "strat1")  # one huge winner
    _close("p2", "ETHUSDT", -50.0, "strat2")
    _close("p3", "ETHUSDT", -50.0, "strat3")
    _close("p4", "ETHUSDT", -50.0, "strat4")

    result = coin_heatmap.compute_coin_heatmap()
    row = next(r for r in result if r["symbol"] == "ETHUSDT")
    assert row["total_pnl"] == 850.0  # big positive total...
    assert row["profitable_strategy_count"] == 1
    assert row["consistency_pct"] == 25.0  # ...but only 1 of 4 strategies actually profited


def test_results_are_sorted_by_consistency_then_total_pnl(test_db):
    _close("p1", "AAAUSDT", 10.0, "strat1")  # 100% consistency, small pnl
    _close("p2", "BBBUSDT", 1000.0, "strat1")
    _close("p3", "BBBUSDT", -10.0, "strat2")  # 50% consistency, huge pnl

    result = coin_heatmap.compute_coin_heatmap()
    symbols_in_order = [r["symbol"] for r in result]
    assert symbols_in_order.index("AAAUSDT") < symbols_in_order.index("BBBUSDT")


def test_respects_the_since_filter(test_db):
    _close("p1", "BTCUSDT", 10.0, "strat1")
    result_excluding = coin_heatmap.compute_coin_heatmap(since_iso="2026-06-01T00:00:00+00:00")
    result_including = coin_heatmap.compute_coin_heatmap(since_iso="2025-01-01T00:00:00+00:00")
    assert result_excluding == []
    assert len(result_including) == 1


def test_empty_when_nothing_closed_yet(test_db):
    assert coin_heatmap.compute_coin_heatmap() == []
