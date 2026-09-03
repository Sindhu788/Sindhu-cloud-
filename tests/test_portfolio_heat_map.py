"""Grand Feature Expansion, Phase 3 Feature 5: Portfolio Heat Map by
strategy and by direction (paper_trading.portfolio.compute_strategy_exposure
/ compute_direction_exposure) -- the pre-existing compute_coin_exposure
already covered "by coin"; these two answer "by strategy" and "by
long/short direction", the two gaps the audit found.
"""

from data_engine import storage
from paper_trading import portfolio


def _open(position_id, symbol, strategy_id, direction, entry_price=100.0, size=1.0, risk_amount=5.0):
    storage.open_paper_position({
        "id": position_id, "exchange": "binance", "symbol": symbol, "direction": direction,
        "entry_price": entry_price, "size": size, "risk_amount": risk_amount,
        "entry_time": 1700000000000, "created_at": "2026-01-01T00:00:00+00:00",
        "strategy_id": strategy_id, "strategy_name": strategy_id,
    })


def test_strategy_exposure_groups_by_strategy_not_coin(test_db):
    _open("p1", "BTCUSDT", "strat1", "long", risk_amount=10.0)
    _open("p2", "ETHUSDT", "strat1", "long", risk_amount=20.0)
    _open("p3", "BTCUSDT", "strat2", "long", risk_amount=5.0)

    result = portfolio.compute_strategy_exposure("binance")
    strat1 = next(r for r in result if r["strategy_id"] == "strat1")
    assert strat1["position_count"] == 2
    assert strat1["coin_count"] == 2
    assert strat1["total_risk"] == 30.0


def test_strategy_exposure_sorted_by_risk_descending(test_db):
    _open("p1", "BTCUSDT", "small", "long", risk_amount=5.0)
    _open("p2", "ETHUSDT", "big", "long", risk_amount=50.0)

    result = portfolio.compute_strategy_exposure("binance")
    assert result[0]["strategy_id"] == "big"


def test_strategy_exposure_empty_with_no_open_positions(test_db):
    assert portfolio.compute_strategy_exposure("binance") == []


def test_direction_exposure_splits_long_and_short(test_db):
    _open("p1", "BTCUSDT", "strat1", "long", entry_price=100.0, size=1.0, risk_amount=10.0)
    _open("p2", "ETHUSDT", "strat1", "short", entry_price=200.0, size=1.0, risk_amount=20.0)

    result = portfolio.compute_direction_exposure("binance")
    assert result["long"]["position_count"] == 1
    assert result["short"]["position_count"] == 1
    assert result["long"]["total_notional"] == 100.0
    assert result["short"]["total_notional"] == 200.0


def test_direction_exposure_pct_of_total_reveals_a_lopsided_portfolio(test_db):
    """The whole point of this feature: every individual strategy could
    look balanced, but the combined portfolio secretly leans one way."""
    _open("p1", "BTCUSDT", "strat1", "long", entry_price=100.0, size=3.0)
    _open("p2", "ETHUSDT", "strat2", "short", entry_price=100.0, size=1.0)

    result = portfolio.compute_direction_exposure("binance")
    assert result["long"]["pct_of_total_notional"] == 75.0
    assert result["short"]["pct_of_total_notional"] == 25.0


def test_direction_exposure_with_no_positions_is_all_zero(test_db):
    result = portfolio.compute_direction_exposure("binance")
    assert result["long"]["position_count"] == 0
    assert result["long"]["pct_of_total_notional"] == 0.0
