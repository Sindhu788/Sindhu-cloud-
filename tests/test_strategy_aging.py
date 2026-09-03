"""Grand Feature Expansion, Phase 3 Feature 12: Strategy Aging Analysis
(paper_trading.insights.compute_strategy_aging) -- a TREND-over-time view,
distinct from every other single-snapshot metric in this module. Splits
closed trades into consecutive windows and compares the oldest half's
average win rate against the newest half's.
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
        "strategy_id": strategy_id, "strategy_name": strategy_id,
    }
    storage.open_paper_position(pos)
    storage.close_paper_position(
        position_id, 100.0 + pnl, 1700000100000, pnl, pnl,
        "take_profit" if pnl >= 0 else "stop_loss", {}, {},
        (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(),
    )


def test_too_few_windows_returns_no_trend(test_db):
    for i in range(15):  # only 1 full window of 10
        _close(f"p{i}", pnl=10.0, days_ago=30 - i)
    result = insights.compute_strategy_aging("strat1")
    assert result["windows"] == []
    assert result["trend"] is None


def test_a_weakening_strategy_is_detected(test_db):
    # 3 windows of 10: oldest window all wins, newest window all losses.
    pnls = [10.0] * 10 + [10.0] * 10 + [-10.0] * 10
    for i, pnl in enumerate(pnls):
        _close(f"p{i}", pnl=pnl, days_ago=30 - i)
    result = insights.compute_strategy_aging("strat1")
    assert result["trend"] == "weakening"
    assert len(result["windows"]) == 3
    assert result["windows"][0]["win_rate_pct"] == 100.0
    assert result["windows"][-1]["win_rate_pct"] == 0.0


def test_an_improving_strategy_is_detected(test_db):
    pnls = [-10.0] * 10 + [-10.0] * 10 + [10.0] * 10
    for i, pnl in enumerate(pnls):
        _close(f"p{i}", pnl=pnl, days_ago=30 - i)
    result = insights.compute_strategy_aging("strat1")
    assert result["trend"] == "improving"


def test_a_stable_strategy_is_detected(test_db):
    # Alternate win/loss consistently across all windows -- ~50% throughout.
    pnls = ([10.0, -10.0] * 5) * 3
    for i, pnl in enumerate(pnls):
        _close(f"p{i}", pnl=pnl, days_ago=30 - i)
    result = insights.compute_strategy_aging("strat1")
    assert result["trend"] == "stable"


def test_windows_are_in_chronological_order(test_db):
    pnls = [10.0] * 30
    for i, pnl in enumerate(pnls):
        _close(f"p{i}", pnl=pnl, days_ago=30 - i)
    result = insights.compute_strategy_aging("strat1")
    periods = [w["period_start"] for w in result["windows"]]
    assert periods == sorted(periods)


def test_strategy_profile_exposes_aging(test_db, monkeypatch):
    from backtest_engine import strategy_library as lib
    from paper_trading import strategy_profile

    monkeypatch.setattr(lib, "list_all", lambda: [{"id": "strat1", "name": "Test Strategy", "status": "active"}])
    for i in range(30):
        _close(f"p{i}", pnl=10.0, days_ago=30 - i)

    profile = strategy_profile.get_strategy_profile("strat1", "binance")
    assert profile["aging"]["trend"] is not None
