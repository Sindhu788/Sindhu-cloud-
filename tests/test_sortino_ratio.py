"""Grand Feature Expansion, Phase 3 Feature 6: Sortino Ratio, added to
paper_trading.insights.compute_risk_metrics() alongside the pre-existing
Sharpe Ratio. Confirms the core distinction the metric exists FOR: a
strategy with big wins and small/no losses scores much higher on Sortino
than on Sharpe (which penalizes upside volatility too), and that the
existing Sharpe/drawdown fields are untouched by this addition.
"""

from datetime import datetime, timezone, timedelta

import pytest

from data_engine import config as base_config, storage
from paper_trading import insights


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _close(position_id, pnl, strategy_id="strat1", days_ago=0):
    pos = {
        "id": position_id, "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": 1700000000000,
        "created_at": (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(),
        "strategy_id": strategy_id, "strategy_name": "Test Strategy",
    }
    storage.open_paper_position(pos)
    storage.close_paper_position(
        position_id, 100.0 + pnl, 1700000100000, pnl, pnl,
        "take_profit" if pnl >= 0 else "stop_loss", {}, {},
        (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(),
    )


def test_too_few_trades_returns_none_for_both_ratios(test_db):
    result = insights.compute_risk_metrics("strat1")
    assert result == {"sharpe_ratio": None, "sortino_ratio": None, "max_drawdown_pct": None,
                       "current_drawdown_pct": None, "sample_size": 0}


def test_no_losing_trades_makes_sortino_undefined_not_infinite(test_db):
    for i, pnl in enumerate([5.0, 15.0, 8.0, 20.0, 12.0]):  # varying, but never a loss
        _close(f"p{i}", pnl=pnl, days_ago=i)
    result = insights.compute_risk_metrics("strat1")
    assert result["sharpe_ratio"] is not None  # real variance among the wins -- Sharpe is defined
    assert result["sortino_ratio"] is None  # no downside deviation at all -- Sortino is undefined, not infinite


def test_a_strategy_with_big_wins_and_small_losses_scores_higher_on_sortino_than_sharpe(test_db):
    pnls = [50.0, 60.0, -2.0, 55.0, -1.0, 45.0, -3.0]
    for i, pnl in enumerate(pnls):
        _close(f"p{i}", pnl=pnl, days_ago=i)

    result = insights.compute_risk_metrics("strat1")
    assert result["sharpe_ratio"] is not None
    assert result["sortino_ratio"] is not None
    # The whole point of Sortino: upside volatility (the big wins) isn't
    # punished, only the small downside moves are -- so it must score
    # higher than Sharpe for this classic "big wins, tiny losses" shape.
    assert result["sortino_ratio"] > result["sharpe_ratio"]


def test_sharpe_and_drawdown_fields_are_unaffected_by_the_sortino_addition(test_db):
    for i, pnl in enumerate([10.0, -5.0, 8.0, -3.0, 12.0]):
        _close(f"p{i}", pnl=pnl, days_ago=i)
    result = insights.compute_risk_metrics("strat1")
    assert set(result.keys()) == {"sharpe_ratio", "sortino_ratio", "max_drawdown_pct", "current_drawdown_pct", "sample_size"}
    assert result["sample_size"] == 5
    assert result["max_drawdown_pct"] is not None
