"""Grand Feature Expansion, Phase 3 Feature 7: Value at Risk (VaR),
paper_trading.insights.compute_value_at_risk() -- historical simulation
(no assumed bell-curve), gated at pattern_stats.MIN_SAMPLE_SIZE (25) like
every other percentile-based statistic in this codebase.
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


def test_below_min_sample_size_returns_none(test_db):
    for i in range(10):
        _close(f"p{i}", pnl=-5.0, days_ago=i)
    result = insights.compute_value_at_risk("strat1")
    assert result["var_amount"] is None
    assert result["sample_size"] == 10
    assert result["min_sample_size"] == pattern_stats.MIN_SAMPLE_SIZE


def test_var_reads_the_real_5th_percentile_loss(test_db):
    # 25 trades: one huge loss (-500), everything else a small +/-10.
    # At 95% confidence the worst ~5% (index 1 of 25 sorted ascending,
    # round(0.05*25)=1) is the SECOND worst trade, not the single huge
    # outlier -- proving this reads a real percentile, not just min().
    for i in range(24):
        _close(f"p{i}", pnl=10.0 if i % 2 == 0 else -10.0, days_ago=i)
    _close("outlier", pnl=-500.0, days_ago=24)

    result = insights.compute_value_at_risk("strat1")
    assert result["sample_size"] == 25
    assert result["var_amount"] == 10.0  # the 2nd-worst trade (-10), not the -500 outlier
    assert result["var_pct_of_trades_worse"] == 5.0


def test_var_is_zero_when_even_the_worst_case_in_range_was_profitable(test_db):
    for i in range(25):
        _close(f"p{i}", pnl=20.0 + i, days_ago=i)  # every trade profitable
    result = insights.compute_value_at_risk("strat1")
    assert result["var_amount"] == 0.0


def test_var_is_scoped_per_strategy(test_db):
    for i in range(25):
        _close(f"p{i}", pnl=-10.0, days_ago=i, strategy_id="strat1")
    for i in range(25):
        _close(f"q{i}", pnl=100.0, days_ago=i, strategy_id="strat2")

    var1 = insights.compute_value_at_risk("strat1")
    var2 = insights.compute_value_at_risk("strat2")
    assert var1["var_amount"] == 10.0
    assert var2["var_amount"] == 0.0


def test_strategy_profile_exposes_value_at_risk(test_db, monkeypatch):
    from backtest_engine import strategy_library as lib
    from paper_trading import strategy_profile

    monkeypatch.setattr(lib, "list_all", lambda: [{"id": "strat1", "name": "Test Strategy", "status": "active"}])
    for i in range(25):
        _close(f"p{i}", pnl=-10.0, days_ago=i, strategy_id="strat1")

    profile = strategy_profile.get_strategy_profile("strat1", "binance")
    assert profile["value_at_risk"]["var_amount"] == 10.0
