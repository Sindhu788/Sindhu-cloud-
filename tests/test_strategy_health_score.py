"""Grand Feature Expansion, Phase 3 Feature 2: Strategy Health Score
(paper_trading.insights.compute_strategy_health_score) -- a single 0-100
composite from win rate, profit factor, drawdown, consistency (Sharpe),
and sample size. A plain, documented weighted sum, not a black box --
every component is returned alongside the total.
"""

from datetime import datetime, timezone, timedelta

import pytest

from data_engine import config as base_config, storage
from paper_trading import insights, pattern_stats


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


def test_zero_trades_returns_no_score_not_zero(test_db):
    result = insights.compute_strategy_health_score("strat1")
    assert result == {"health_score": None, "components": None, "sample_size": 0}


def test_score_is_bounded_0_to_100(test_db):
    for i, pnl in enumerate([10.0, -5.0, 8.0, -3.0, 12.0, -2.0, 15.0]):
        _close(f"p{i}", pnl=pnl, days_ago=i)
    result = insights.compute_strategy_health_score("strat1")
    assert 0.0 <= result["health_score"] <= 100.0
    # Every component sums to exactly the total -- no hidden adjustment.
    c = result["components"]
    total = (c["win_rate_score"] + c["profit_factor_score"] + c["drawdown_score"]
             + c["consistency_score"] + c["sample_size_score"])
    # Compares the SUM OF ALREADY-ROUNDED components against the total
    # (itself rounded from the unrounded components) -- allow a 0.1
    # tolerance for compounding rounding, not exact equality.
    assert abs(total - result["health_score"]) <= 0.15


def test_a_strong_strategy_scores_high(test_db):
    # 25 trades, ~84% win rate, big wins small losses, gives a real
    # sample size, good PF, good Sharpe, low drawdown.
    pnls = [30.0] * 21 + [-5.0] * 4
    for i, pnl in enumerate(pnls):
        _close(f"p{i}", pnl=pnl, days_ago=i)
    result = insights.compute_strategy_health_score("strat1")
    assert result["health_score"] >= 70.0
    assert result["sample_size"] == 25


def test_a_weak_strategy_scores_low(test_db):
    # Mostly losses, a couple of small wins -- poor win rate and PF.
    pnls = [-30.0] * 20 + [5.0] * 5
    for i, pnl in enumerate(pnls):
        _close(f"p{i}", pnl=pnl, days_ago=i)
    result = insights.compute_strategy_health_score("strat1")
    assert result["health_score"] <= 40.0


def test_no_losing_trades_gives_full_profit_factor_marks_not_a_fabricated_number(test_db):
    for i in range(5):
        _close(f"p{i}", pnl=10.0, days_ago=i)
    result = insights.compute_strategy_health_score("strat1")
    assert result["components"]["profit_factor"] is None  # never fabricates an "infinite" PF as a real number
    assert result["components"]["profit_factor_score"] == 30.0  # but still scores full marks for it


def test_small_sample_size_caps_the_sample_component(test_db):
    _close("p1", pnl=10.0, days_ago=0)
    result = insights.compute_strategy_health_score("strat1")
    expected = round(1 / pattern_stats.MIN_SAMPLE_SIZE * 10.0, 1)
    assert result["components"]["sample_size_score"] == expected


def test_score_is_scoped_per_strategy(test_db):
    for i in range(10):
        _close(f"p{i}", pnl=10.0, days_ago=i, strategy_id="strat1")
    for i in range(10):
        _close(f"q{i}", pnl=-10.0, days_ago=i, strategy_id="strat2")

    score1 = insights.compute_strategy_health_score("strat1")
    score2 = insights.compute_strategy_health_score("strat2")
    assert score1["health_score"] > score2["health_score"]


def test_strategy_profile_exposes_health_score(test_db, monkeypatch):
    from backtest_engine import strategy_library as lib
    from paper_trading import strategy_profile

    monkeypatch.setattr(lib, "list_all", lambda: [{"id": "strat1", "name": "Test Strategy", "status": "active"}])
    for i in range(10):
        _close(f"p{i}", pnl=10.0, days_ago=i)

    profile = strategy_profile.get_strategy_profile("strat1", "binance")
    assert profile["health_score"]["health_score"] is not None


def test_strategy_profile_exposes_archived_flag_for_the_health_badge(test_db, monkeypatch):
    """Grand Feature Expansion, Phase 4 Feature 11: Health Badge is
    computed client-side from health_score + this archived flag -- no new
    backend computation, just this one field needed to be exposed."""
    from backtest_engine import strategy_library as lib
    from paper_trading import strategy_profile

    monkeypatch.setattr(lib, "list_all", lambda: [
        {"id": "strat1", "name": "Test Strategy", "status": "active", "archived": True},
    ])
    profile = strategy_profile.get_strategy_profile("strat1", "binance")
    assert profile["archived"] is True
