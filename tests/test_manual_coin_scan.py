"""Master Task Expansion, Part 6: Manual Scan -- Scan Selected Coin.
See paper_trading/engine.py's run_single_coin_scan_now() docstring.
"""
from unittest.mock import MagicMock, patch

from paper_trading import coin_blacklist, kill_switch
from paper_trading.engine import PaperTradingEngine


def _fresh_engine():
    return PaperTradingEngine()


def test_scan_refuses_when_kill_switch_active():
    engine = _fresh_engine()
    with patch.object(kill_switch, "is_active", return_value=True):
        result = engine.run_single_coin_scan_now("BTCUSDT")
    assert result["skipped"] is True
    assert "kill switch" in result["reason"]


def test_scan_refuses_a_blacklisted_coin():
    engine = _fresh_engine()
    with patch.object(kill_switch, "is_active", return_value=False), \
         patch.object(coin_blacklist, "filter_out_blacklisted", return_value=[]):
        result = engine.run_single_coin_scan_now("SCAMUSDT")
    assert result["skipped"] is True
    assert "blacklist" in result["reason"]


def test_scan_runs_the_real_per_coin_pipeline_for_an_allowed_coin():
    engine = _fresh_engine()
    with patch.object(kill_switch, "is_active", return_value=False), \
         patch.object(coin_blacklist, "filter_out_blacklisted", return_value=["BTCUSDT"]), \
         patch("paper_trading.engine.market_state") as fake_market_state, \
         patch.object(engine, "_process_coin", return_value=(1, 2)) as fake_process:
        fake_market_state.classify.return_value = {"market_state": "trending"}
        result = engine.run_single_coin_scan_now("BTCUSDT")
    assert result == {"symbol": "BTCUSDT", "skipped": False, "market_state": "trending", "opened": 1, "rejected": 2}
    fake_process.assert_called_once()


def test_scan_reports_a_real_market_classification_error_without_crashing():
    engine = _fresh_engine()
    with patch.object(kill_switch, "is_active", return_value=False), \
         patch.object(coin_blacklist, "filter_out_blacklisted", return_value=["WEIRDUSDT"]), \
         patch("paper_trading.engine.market_state") as fake_market_state:
        fake_market_state.classify.side_effect = RuntimeError("exchange unreachable")
        result = engine.run_single_coin_scan_now("WEIRDUSDT")
    assert result["skipped"] is False
    assert "exchange unreachable" in result["error"]
