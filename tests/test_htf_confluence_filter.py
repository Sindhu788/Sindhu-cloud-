"""Master Task 6, 2.3 -- HTF Confluence Filter unit tests. Mocks
data_engine.resample.get_ohlcv so these never touch real network/candle
data -- only paper_trading.htf_confluence_filter's own decision logic is
under test here (backtest_engine.concepts.valid_structure_trend itself is
already covered by its own existing tests)."""

from unittest.mock import patch

import pandas as pd

from paper_trading import htf_confluence_filter as htf


def _fake_df(n=20):
    return pd.DataFrame({
        "open": [1.0] * n, "high": [1.1] * n, "low": [0.9] * n, "close": [1.0] * n, "volume": [100.0] * n,
    })


def test_higher_timeframes_for_matches_the_tasks_own_example():
    """The task's explicit example: a 15-minute entry checks 1h and 4h."""
    assert htf.higher_timeframes_for("15m") == ["1h", "4h"]


def test_unconfigured_entry_timeframe_never_blocks():
    allowed, reason = htf.check("binance", "BTCUSDT", "unknown_tf", "bullish")
    assert allowed is True
    assert reason is None


def test_bullish_signal_allowed_when_htf_trend_agrees():
    with patch.object(htf, "htf_trend", return_value="up"):
        allowed, reason = htf.check("binance", "BTCUSDT", "15m", "bullish")
    assert allowed is True


def test_bullish_signal_blocked_when_htf_trend_contradicts():
    with patch.object(htf, "htf_trend", return_value="down"):
        allowed, reason = htf.check("binance", "BTCUSDT", "15m", "bullish")
    assert allowed is False
    assert "contradicts" in reason


def test_bearish_signal_blocked_when_htf_trend_is_up():
    with patch.object(htf, "htf_trend", return_value="up"):
        allowed, reason = htf.check("binance", "BTCUSDT", "15m", "bearish")
    assert allowed is False


def test_no_established_htf_trend_never_blocks():
    """None (not enough data / no valid swing broken yet) must never be
    treated as a contradiction -- a coin with no settled HTF structure yet
    must not permanently block every strategy using this filter."""
    with patch.object(htf, "htf_trend", return_value=None):
        allowed, reason = htf.check("binance", "BTCUSDT", "15m", "bullish")
    assert allowed is True


def test_htf_trend_reads_real_ohlcv_and_reports_insufficient_data_as_none():
    with patch.object(htf, "get_ohlcv", return_value=_fake_df(n=3)):
        assert htf.htf_trend("binance", "BTCUSDT", "1h") is None
