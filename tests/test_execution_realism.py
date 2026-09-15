"""Grand Master Batch #2, Phase 1.2: real evidence that paper trading no
longer assumes a perfect fill.

1. Spread (bid/ask gap) is now applied on both entry and exit, on top of
   the slippage already applied before this batch -- backtest_engine.engine
   already modeled both separately for backtests; paper trading only ever
   applied slippage.
2. The Slippage-Aware Entry Filter (paper_trading/slippage_filter.py --
   rejects an entry when realistic slippage would eat too much of the
   trade's own stop distance, a real missed/adverse-fill risk protection)
   is now ON by default, directly implementing the "missed-fill scenario"
   half of this phase's ask.
"""

from unittest.mock import patch

import pandas as pd
import pytest

from backtest_engine.engine import _apply_slippage, _apply_spread
from data_engine import config as base_config, feature_toggles
from paper_trading import position_manager, risk_manager, slippage_filter


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


def test_open_position_applies_both_slippage_and_spread_on_entry(test_db):
    cand = _candidate(direction="bullish", entry_price=100.0)
    pos = position_manager.open_position("binance", "BTCUSDT", cand, size=1.0, risk_amount=1.0,
                                          confidence=80.0, market_snapshot={})
    slippage_only = _apply_slippage(100.0, "long", False, 0.0005)
    both = _apply_spread(slippage_only, "long", False, position_manager._SPREAD_PCT)
    assert pos["entry_price"] == pytest.approx(both)
    # A real fill worse than slippage alone -- proves spread is a genuinely
    # separate, additional cost, not a no-op or folded into slippage.
    assert pos["entry_price"] > slippage_only


def test_close_applies_both_slippage_and_spread_on_exit(test_db):
    cand = _candidate(direction="bullish", entry_price=100.0)
    pos = position_manager.open_position("binance", "BTCUSDT", cand, size=1.0, risk_amount=1.0,
                                          confidence=80.0, market_snapshot={})
    closed = position_manager._close(pos, 110.0, "take_profit")
    slippage_only = _apply_slippage(110.0, "long", True, 0.0005)
    both = _apply_spread(slippage_only, "long", True, position_manager._SPREAD_PCT)
    assert closed["exit_price"] == pytest.approx(both)
    assert closed["exit_price"] < slippage_only


def test_short_side_spread_direction_is_also_against_the_trader(test_db):
    cand = _candidate(direction="bearish", entry_price=100.0, stop_loss=101.0, take_profit=96.0)
    pos = position_manager.open_position("binance", "BTCUSDT", cand, size=1.0, risk_amount=1.0,
                                          confidence=80.0, market_snapshot={})
    # A short's worse entry fill is LOWER (sells for less than the raw
    # signal price), same directional convention _apply_spread documents.
    assert pos["entry_price"] < 100.0


def test_slippage_aware_filter_is_now_on_by_default():
    toggles = feature_toggles.get_toggles()
    assert toggles["slippage_aware_filter_enabled"] is True


def test_slippage_aware_filter_now_actually_rejects_a_real_tight_stop_entry_by_default(test_db):
    """End-to-end through risk_manager.evaluate() with NOTHING explicitly
    enabled by the test -- proves this is genuinely the new default
    behavior, not something only visible when a test opts in."""
    fake_ohlcv = pd.DataFrame({
        "high": [101.0] * 24, "low": [95.0] * 24, "close": [98.0] * 24,  # ~6% avg range -> ~0.3% estimated slippage
    })
    cand = _candidate(direction="bullish", entry_price=100.0, stop_loss=100.1)  # razor-thin stop distance
    settings = {"initial_balance": 10000.0, "risk_pct_default": 1.0, "max_open_trades": 5}
    with patch.object(slippage_filter, "get_ohlcv", return_value=fake_ohlcv):
        approved, reason, size, risk = risk_manager.evaluate("strat1", "BTCUSDT", cand, settings, exchange="binance")
    assert approved is False
    assert "slippage-aware filter" in reason
