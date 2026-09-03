"""Grand Feature Expansion, Phase 5 Feature 11: Best Combination
Auto-Suggest, extended to a multi-strategy portfolio
(paper_trading/challenge_analysis.py's suggest_best_portfolio). Distinct
from the existing best_combination/top_combinations (single best strategy+
coin PAIR) -- this suggests several DIFFERENT strategies together. Purely
informational, never activates anything.
"""

from datetime import datetime, timezone

from data_engine import storage
from paper_trading import challenge_analysis, pattern_stats


def _close_many(strategy_id, symbol, count, pnl=10.0):
    for i in range(count):
        position_id = f"{strategy_id}_{symbol}_{i}"
        created_at = datetime.now(timezone.utc).isoformat()
        storage.open_paper_position({
            "id": position_id, "exchange": "binance", "symbol": symbol, "direction": "long",
            "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
            "entry_time": 1700000000000, "created_at": created_at,
            "strategy_id": strategy_id, "strategy_name": strategy_id,
        })
        storage.close_paper_position(position_id, 100.0 + pnl, 1700000100000, pnl, pnl,
                                      "take_profit", {}, {}, created_at, book_key=strategy_id)


def test_no_trades_yet_suggests_nothing(test_db):
    result = challenge_analysis.suggest_best_portfolio()
    assert result["portfolio"] == []
    assert "no strategy" in result["reason"].lower() or "nothing" in result["reason"].lower()


def test_below_min_sample_size_is_excluded(test_db):
    _close_many("stratA", "BTCUSDT", pattern_stats.MIN_SAMPLE_SIZE - 1)
    result = challenge_analysis.suggest_best_portfolio()
    assert result["portfolio"] == []


def test_trusted_combination_is_suggested(test_db):
    _close_many("stratA", "BTCUSDT", pattern_stats.MIN_SAMPLE_SIZE, pnl=10.0)
    result = challenge_analysis.suggest_best_portfolio()
    assert len(result["portfolio"]) == 1
    assert result["portfolio"][0]["strategy_id"] == "stratA"
    assert result["combined_pnl"] == pattern_stats.MIN_SAMPLE_SIZE * 10.0


def test_never_suggests_the_same_strategy_twice(test_db):
    # stratA trades two coins profitably -- only its single BEST coin
    # should appear, never both.
    _close_many("stratA", "BTCUSDT", pattern_stats.MIN_SAMPLE_SIZE, pnl=20.0)
    _close_many("stratA", "ETHUSDT", pattern_stats.MIN_SAMPLE_SIZE, pnl=10.0)
    result = challenge_analysis.suggest_best_portfolio(top_n=3)
    strategy_ids = [p["strategy_id"] for p in result["portfolio"]]
    assert strategy_ids.count("stratA") == 1
    assert result["portfolio"][0]["symbol"] == "BTCUSDT"  # the higher-PnL coin wins


def test_respects_top_n(test_db):
    for i in range(5):
        _close_many(f"strat{i}", "BTCUSDT", pattern_stats.MIN_SAMPLE_SIZE, pnl=float(i + 1))
    result = challenge_analysis.suggest_best_portfolio(top_n=2)
    assert len(result["portfolio"]) == 2


def test_endpoint_returns_suggestion(test_db):
    from sindhu_web.api.paper_trading import get_best_portfolio_suggestion

    _close_many("stratA", "BTCUSDT", pattern_stats.MIN_SAMPLE_SIZE, pnl=10.0)
    result = get_best_portfolio_suggestion(top_n=3)
    assert len(result["portfolio"]) == 1
