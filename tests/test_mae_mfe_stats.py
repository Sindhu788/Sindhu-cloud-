"""Grand Feature Expansion, Phase 3 Feature 8: aggregate MAE/MFE
(paper_trading.insights.compute_mae_mfe_stats) -- split by winners vs
losers, since "how much heat did winners take" and "how far did losers
run in profit first" are different, both useful questions.
"""

from data_engine import config as base_config, storage
from paper_trading import insights

import pytest


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _closed_trade(position_id, pnl, tick_low, tick_high, strategy_id="strat1"):
    storage.open_paper_position({
        "id": position_id, "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": 1700000000000, "created_at": "2026-01-01T00:00:00+00:00",
        "strategy_id": strategy_id, "strategy_name": strategy_id,
    })
    storage.update_position_excursion(position_id, tick_low, tick_high)
    storage.close_paper_position(position_id, 100.0 + pnl, 1700000100000, pnl, pnl,
                                  "take_profit" if pnl >= 0 else "stop_loss", {}, {}, "2026-01-02T00:00:00+00:00")


def test_no_data_reports_zero_sample_size(test_db):
    result = insights.compute_mae_mfe_stats("strat1")
    assert result == {"sample_size": 0, "winners": None, "losers": None}


def test_splits_winners_and_losers_separately(test_db):
    # Winner: dipped to 90 (MAE=-10) before closing up +20.
    _closed_trade("p1", pnl=20.0, tick_low=90.0, tick_high=125.0)
    # Loser: ran up to 115 (MFE=+15) before closing down -10.
    _closed_trade("p2", pnl=-10.0, tick_low=85.0, tick_high=115.0)

    result = insights.compute_mae_mfe_stats("strat1")
    assert result["sample_size"] == 2
    assert result["winners"]["count"] == 1
    assert result["winners"]["avg_mae"] == -10.0
    assert result["losers"]["count"] == 1
    assert result["losers"]["avg_mfe"] == 15.0


def test_averages_across_multiple_winners(test_db):
    _closed_trade("p1", pnl=10.0, tick_low=95.0, tick_high=110.0)  # MAE -5
    _closed_trade("p2", pnl=10.0, tick_low=85.0, tick_high=110.0)  # MAE -15
    result = insights.compute_mae_mfe_stats("strat1")
    assert result["winners"]["avg_mae"] == -10.0  # average of -5 and -15


def test_scoped_per_strategy(test_db):
    _closed_trade("p1", pnl=10.0, tick_low=90.0, tick_high=110.0, strategy_id="strat1")
    _closed_trade("p2", pnl=10.0, tick_low=95.0, tick_high=110.0, strategy_id="strat2")
    result = insights.compute_mae_mfe_stats("strat1")
    assert result["sample_size"] == 1


def test_only_winners_no_losers_yet(test_db):
    _closed_trade("p1", pnl=10.0, tick_low=90.0, tick_high=110.0)
    result = insights.compute_mae_mfe_stats("strat1")
    assert result["winners"] is not None
    assert result["losers"] is None
