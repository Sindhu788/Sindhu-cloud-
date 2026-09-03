"""Grand Feature Expansion, Phase 7 Feature 1: Duplicate Exposure Warning
(paper_trading/portfolio.py's detect_duplicate_exposure_warnings) --
flags when 2+ INDEPENDENT strategies are all trading the SAME coin right
now, purely on strategy_count. Genuinely distinct from
paper_trading.correlation.py's warning, which requires two DIFFERENT
symbols to be statistically price-correlated.
"""

from datetime import datetime, timezone

from data_engine import storage
from paper_trading import portfolio


def _open_position(position_id, symbol, strategy_id, risk_amount=10.0):
    storage.open_paper_position({
        "id": position_id, "exchange": "binance", "symbol": symbol, "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": risk_amount,
        "entry_time": 1700000000000, "created_at": datetime.now(timezone.utc).isoformat(),
        "strategy_id": strategy_id, "strategy_name": strategy_id,
    })


def test_no_open_positions_yields_no_warnings(test_db):
    assert portfolio.detect_duplicate_exposure_warnings("binance") == []


def test_single_strategy_on_a_coin_is_not_a_warning(test_db):
    _open_position("p1", "BTCUSDT", "stratA")
    assert portfolio.detect_duplicate_exposure_warnings("binance") == []


def test_two_strategies_on_the_same_coin_triggers_a_warning(test_db):
    _open_position("p1", "BTCUSDT", "stratA")
    _open_position("p2", "BTCUSDT", "stratB")
    warnings = portfolio.detect_duplicate_exposure_warnings("binance")
    assert len(warnings) == 1
    assert warnings[0]["symbol"] == "BTCUSDT"
    assert warnings[0]["strategy_count"] == 2
    assert "BTCUSDT" in warnings[0]["message"]


def test_different_coins_each_with_one_strategy_yields_no_warnings(test_db):
    _open_position("p1", "BTCUSDT", "stratA")
    _open_position("p2", "ETHUSDT", "stratB")
    assert portfolio.detect_duplicate_exposure_warnings("binance") == []


def test_respects_a_custom_min_strategies_threshold(test_db):
    _open_position("p1", "BTCUSDT", "stratA")
    _open_position("p2", "BTCUSDT", "stratB")
    _open_position("p3", "BTCUSDT", "stratC")
    assert len(portfolio.detect_duplicate_exposure_warnings("binance", min_strategies=3)) == 1
    assert len(portfolio.detect_duplicate_exposure_warnings("binance", min_strategies=4)) == 0


def test_endpoint_returns_warnings(test_db, monkeypatch):
    from data_engine import config as base_config
    from sindhu_web.api.paper_trading import get_duplicate_exposure_warnings

    _open_position("p1", "BTCUSDT", "stratA")
    _open_position("p2", "BTCUSDT", "stratB")
    result = get_duplicate_exposure_warnings()
    assert len(result["warnings"]) == 1
