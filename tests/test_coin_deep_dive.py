"""Grand Feature Expansion, Phase 3 Feature 17: Coin-Specific Deep-Dive
(paper_trading.coin_heatmap.compute_coin_deep_dive) -- pick one coin, see
every strategy's own performance on it, side by side. Reuses the same raw
matrix the Coin-Performance Heatmap (Feature 3) is built from.
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


def test_lists_every_strategys_own_performance_on_the_coin(test_db):
    _close("p1", "BTCUSDT", 30.0, "strat1")
    _close("p2", "BTCUSDT", -10.0, "strat2")
    _close("p3", "ETHUSDT", 100.0, "strat1")  # a different coin -- must not leak in

    result = coin_heatmap.compute_coin_deep_dive("BTCUSDT")
    assert result["symbol"] == "BTCUSDT"
    assert result["strategy_count"] == 2
    strategy_ids = {s["strategy_id"] for s in result["strategies"]}
    assert strategy_ids == {"strat1", "strat2"}
    assert result["total_pnl"] == 20.0
    assert result["profitable_strategy_count"] == 1


def test_strategies_sorted_by_pnl_descending(test_db):
    _close("p1", "BTCUSDT", -10.0, "worst")
    _close("p2", "BTCUSDT", 50.0, "best")

    result = coin_heatmap.compute_coin_deep_dive("BTCUSDT")
    assert result["strategies"][0]["strategy_id"] == "best"
    assert result["strategies"][1]["strategy_id"] == "worst"


def test_a_coin_with_no_trades_returns_empty_not_an_error(test_db):
    result = coin_heatmap.compute_coin_deep_dive("NEVERUSDT")
    assert result["strategy_count"] == 0
    assert result["strategies"] == []
    assert result["total_pnl"] == 0.0


def test_respects_the_since_filter(test_db):
    _close("p1", "BTCUSDT", 10.0, "strat1")
    excluding = coin_heatmap.compute_coin_deep_dive("BTCUSDT", since_iso="2026-06-01T00:00:00+00:00")
    including = coin_heatmap.compute_coin_deep_dive("BTCUSDT", since_iso="2025-01-01T00:00:00+00:00")
    assert excluding["strategy_count"] == 0
    assert including["strategy_count"] == 1
