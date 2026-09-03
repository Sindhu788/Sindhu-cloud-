"""Grand Feature Expansion, Phase 5 Feature 8: Slippage-Aware Entry Filter
(paper_trading/slippage_filter.py) -- rejects a real entry when the
symbol's own recent volatility suggests expected slippage would eat too
much of the trade's stop-distance risk budget. Genuinely distinct from
Phase 3's slippage_sensitivity_test (backtest-only, after-the-fact PnL
recompute on already-closed trades) -- this runs BEFORE a real entry.
"""

import pandas as pd
import pytest

from data_engine import config as base_config
from paper_trading import risk_manager, slippage_filter


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _fake_df(high_low_range_pct, n=24):
    close = 100.0
    return pd.DataFrame({
        "high": [close * (1 + high_low_range_pct / 2)] * n,
        "low": [close * (1 - high_low_range_pct / 2)] * n,
        "close": [close] * n,
    })


def test_not_enough_candles_returns_none(monkeypatch):
    monkeypatch.setattr(slippage_filter, "get_ohlcv", lambda *a, **k: pd.DataFrame({"high": [], "low": [], "close": []}))
    assert slippage_filter.estimate_slippage_pct("binance", "BTCUSDT") is None


def test_estimate_scales_down_the_raw_candle_range(monkeypatch):
    monkeypatch.setattr(slippage_filter, "get_ohlcv", lambda *a, **k: _fake_df(0.10))
    est = slippage_filter.estimate_slippage_pct("binance", "BTCUSDT")
    assert est == pytest.approx(0.10 * slippage_filter._RANGE_TO_SLIPPAGE_FACTOR)


def test_check_entry_fails_open_when_no_estimate(monkeypatch):
    monkeypatch.setattr(slippage_filter, "estimate_slippage_pct", lambda *a, **k: None)
    ok, reason, est = slippage_filter.check_entry("binance", "BTCUSDT", "long", 100.0, 95.0)
    assert ok is True
    assert reason is None
    assert est is None


def test_check_entry_approves_a_tight_slippage_relative_to_a_wide_stop(monkeypatch):
    monkeypatch.setattr(slippage_filter, "estimate_slippage_pct", lambda *a, **k: 0.001)  # 0.1%
    ok, reason, est = slippage_filter.check_entry("binance", "BTCUSDT", "long", 100.0, 90.0)  # $10 stop distance
    assert ok is True


def test_check_entry_rejects_when_slippage_eats_the_stop_distance(monkeypatch):
    monkeypatch.setattr(slippage_filter, "estimate_slippage_pct", lambda *a, **k: 0.05)  # 5% -- huge relative to a tight stop
    ok, reason, est = slippage_filter.check_entry("binance", "BTCUSDT", "long", 100.0, 99.5)  # $0.50 stop distance
    assert ok is False
    assert "slippage" in reason


def test_zero_stop_distance_never_crashes(monkeypatch):
    monkeypatch.setattr(slippage_filter, "estimate_slippage_pct", lambda *a, **k: 0.01)
    ok, reason, est = slippage_filter.check_entry("binance", "BTCUSDT", "long", 100.0, 100.0)
    assert ok is True


def test_disabled_by_default_never_affects_risk_manager(test_db):
    settings = {"initial_balance": 10000.0, "risk_pct_default": 1.0, "max_open_trades": 5}
    candidate = {"stop_loss": 99.99, "entry_price": 100.0, "direction": "bullish"}
    approved, reason, size, risk_amount = risk_manager.evaluate("strat1", "BTCUSDT", candidate, settings, exchange="binance")
    assert approved is True


def test_enabled_and_failing_rejects_the_trade(test_db, monkeypatch):
    monkeypatch.setattr(risk_manager.feature_toggles, "is_enabled", lambda key: key == "slippage_aware_filter_enabled")
    monkeypatch.setattr(slippage_filter, "check_entry", lambda *a, **k: (False, "expected slippage would eat over 50% of this trade's stop distance", 0.05))
    settings = {"initial_balance": 10000.0, "risk_pct_default": 1.0, "max_open_trades": 5}
    candidate = {"stop_loss": 99.99, "entry_price": 100.0, "direction": "bullish"}
    approved, reason, size, risk_amount = risk_manager.evaluate("strat1", "BTCUSDT", candidate, settings, exchange="binance")
    assert approved is False
    assert "slippage-aware filter" in reason
