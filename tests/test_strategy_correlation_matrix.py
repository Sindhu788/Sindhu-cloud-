"""Grand Feature Expansion, Phase 3 Feature 4: Strategy-vs-Strategy
Correlation Matrix (paper_trading.correlation.strategy_correlation_matrix)
-- distinct from the pre-existing detect_warnings() in the same module,
which correlates SYMBOL PRICE RETURNS for currently-open positions. This
correlates each strategy's own daily REALIZED PnL time series.
"""

from datetime import datetime, timezone, timedelta

from data_engine import storage
from paper_trading import correlation


def _close(position_id, pnl, strategy_id, days_ago):
    closed_at = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    pos = {
        "id": position_id, "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": 1700000000000, "created_at": closed_at,
        "strategy_id": strategy_id, "strategy_name": strategy_id,
    }
    storage.open_paper_position(pos)
    storage.close_paper_position(position_id, 100.0 + pnl, 1700000100000, pnl, pnl,
                                  "take_profit" if pnl >= 0 else "stop_loss", {}, {}, closed_at)


def test_diagonal_is_1_when_a_strategy_has_data(test_db):
    for d in range(12):
        _close(f"p{d}", pnl=10.0, strategy_id="strat1", days_ago=d)
    result = correlation.strategy_correlation_matrix(["strat1"])
    assert result["matrix"][0][0] == 1.0


def test_two_strategies_that_win_and_lose_together_are_highly_correlated(test_db):
    for d in range(15):
        pnl = 10.0 if d % 2 == 0 else -10.0
        _close(f"a{d}", pnl=pnl, strategy_id="strat1", days_ago=d)
        _close(f"b{d}", pnl=pnl * 2, strategy_id="strat2", days_ago=d)  # same sign, different magnitude

    result = correlation.strategy_correlation_matrix(["strat1", "strat2"])
    assert result["matrix"][0][1] >= 0.9
    assert result["matrix"][1][0] == result["matrix"][0][1]  # symmetric


def test_two_strategies_that_move_opposite_are_negatively_correlated(test_db):
    for d in range(15):
        pnl = 10.0 if d % 2 == 0 else -10.0
        _close(f"a{d}", pnl=pnl, strategy_id="strat1", days_ago=d)
        _close(f"b{d}", pnl=-pnl, strategy_id="strat2", days_ago=d)  # opposite sign

    result = correlation.strategy_correlation_matrix(["strat1", "strat2"])
    assert result["matrix"][0][1] <= -0.9


def test_too_few_overlapping_days_returns_none_not_a_misleading_number(test_db):
    for d in range(3):
        _close(f"a{d}", pnl=10.0, strategy_id="strat1", days_ago=d)
        _close(f"b{d}", pnl=10.0, strategy_id="strat2", days_ago=d)

    result = correlation.strategy_correlation_matrix(["strat1", "strat2"])
    assert result["matrix"][0][1] is None


def test_a_strategy_with_no_data_correlates_with_nothing(test_db):
    for d in range(15):
        _close(f"a{d}", pnl=10.0, strategy_id="strat1", days_ago=d)
    result = correlation.strategy_correlation_matrix(["strat1", "strat_no_data"])
    assert result["matrix"][0][1] is None
    assert result["matrix"][1][1] is None  # diagonal for a strategy with zero data is also None, not a fake 1.0


def test_only_days_within_the_lookback_window_are_considered(test_db):
    for d in range(15):
        _close(f"a{d}", pnl=10.0 if d % 2 == 0 else -10.0, strategy_id="strat1", days_ago=d)
        _close(f"b{d}", pnl=10.0 if d % 2 == 0 else -10.0, strategy_id="strat2", days_ago=d)
    # Add old, OPPOSITE-signed data far outside a short lookback window --
    # if this leaked in, it would drag the correlation down.
    for d in range(100, 115):
        _close(f"old_a{d}", pnl=10.0, strategy_id="strat1", days_ago=d)
        _close(f"old_b{d}", pnl=-10.0, strategy_id="strat2", days_ago=d)

    result = correlation.strategy_correlation_matrix(["strat1", "strat2"], lookback_days=30)
    assert result["matrix"][0][1] >= 0.9
