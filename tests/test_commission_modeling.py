"""Phase 8 verification, Finding 3: paper trading modeled slippage and
spread but no commission, unlike backtest_engine.engine (which already has
its own commission_pct setting and commission_cost computation) -- paper
PnL ran somewhat better than a real funded account would. Adds a real
per-trade commission (default 0.1%, Binance spot's standard taker fee),
deducted at close the same way backtest_engine already does:
(entry_price + exit_price) * size * commission_pct.
"""

import pytest

from data_engine import config as base_config
from paper_trading import config as pt_config, position_manager


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _candidate(direction="bullish", entry_price=100.0, stop_loss=99.0, take_profit=104.0):
    return {
        "direction": direction, "entry_price": entry_price, "stop_loss": stop_loss,
        "take_profit": take_profit, "stop_loss_type": "structure", "entry_reason": "test",
        "strategy_id": "strat1", "strategy_name": "Test", "strategy_version": 1,
        "lesson_ids": [], "timeframe": "15m",
    }


def test_default_commission_pct_is_binance_spot_taker_fee():
    assert pt_config.load()["commission_pct"] == 0.001


def test_close_deducts_a_real_commission_from_pnl(test_db):
    cand = _candidate(direction="bullish", entry_price=100.0)
    pos = position_manager.open_position("binance", "BTCUSDT", cand, size=1.0, risk_amount=1.0,
                                          confidence=80.0, market_snapshot={})
    closed = position_manager._close(pos, 110.0, "take_profit")

    gross_pnl = (closed["exit_price"] - pos["entry_price"]) * pos["size"]
    expected_commission = (pos["entry_price"] + closed["exit_price"]) * pos["size"] * 0.001
    assert closed["pnl"] == pytest.approx(gross_pnl - expected_commission)
    # A profitable trade's net PnL must be strictly less than its gross --
    # proves the fee is a genuine additional cost, not a no-op.
    assert closed["pnl"] < gross_pnl


def test_short_side_commission_also_reduces_net_pnl(test_db):
    cand = _candidate(direction="bearish", entry_price=100.0, stop_loss=101.0, take_profit=90.0)
    pos = position_manager.open_position("binance", "BTCUSDT", cand, size=1.0, risk_amount=1.0,
                                          confidence=80.0, market_snapshot={})
    closed = position_manager._close(pos, 90.0, "take_profit")
    gross_pnl = (pos["entry_price"] - closed["exit_price"]) * pos["size"]
    assert closed["pnl"] < gross_pnl


def test_commission_pct_set_to_zero_matches_pre_feature_behavior(test_db, monkeypatch):
    original_load = pt_config.load
    monkeypatch.setattr(pt_config, "load", lambda: {**original_load(), "commission_pct": 0.0})
    cand = _candidate(direction="bullish", entry_price=100.0)
    pos = position_manager.open_position("binance", "BTCUSDT", cand, size=1.0, risk_amount=1.0,
                                          confidence=80.0, market_snapshot={})
    closed = position_manager._close(pos, 110.0, "take_profit")
    gross_pnl = (closed["exit_price"] - pos["entry_price"]) * pos["size"]
    assert closed["pnl"] == pytest.approx(gross_pnl)


def test_missing_commission_pct_key_falls_back_to_the_documented_default(test_db, monkeypatch):
    """A settings file saved before this feature existed has no
    commission_pct key at all -- must fall back to the real default, not
    silently charge zero."""
    monkeypatch.setattr(pt_config, "load", lambda: {"initial_balance": 10000.0})
    cand = _candidate(direction="bullish", entry_price=100.0)
    pos = position_manager.open_position("binance", "BTCUSDT", cand, size=1.0, risk_amount=1.0,
                                          confidence=80.0, market_snapshot={})
    closed = position_manager._close(pos, 110.0, "take_profit")
    gross_pnl = (closed["exit_price"] - pos["entry_price"]) * pos["size"]
    expected_commission = (pos["entry_price"] + closed["exit_price"]) * pos["size"] * 0.001
    assert closed["pnl"] == pytest.approx(gross_pnl - expected_commission)
