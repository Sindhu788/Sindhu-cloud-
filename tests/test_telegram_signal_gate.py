"""Tests for Task 1: Telegram branding ("Trade Vision" in messages only)
and the statistical-confidence gate on automatic signal sending, reusing
paper_trading.pattern_stats (Wilson score, min. 25 trades) exactly as the
Genuine Evolution Engine already does for Pattern Auto-Avoid/Lesson
Auto-Apply -- no new threshold invented here.
"""

from unittest.mock import patch

import pytest

from data_engine import config as base_config, storage
from paper_trading import telegram_bot, pattern_stats


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _position(**overrides):
    base = {
        "id": "pos1", "strategy_id": "strat1", "strategy_name": "Test Strategy",
        "symbol": "BTCUSDT", "direction": "long", "entry_price": 100.0,
        "stop_loss": 95.0, "take_profit": 110.0, "market_state": "trending_up",
        "session": "london", "entry_reason": "test",
    }
    base.update(overrides)
    return base


def _open_position(storage_mod, **overrides):
    pos = _position(**overrides)
    pos.update({
        "exchange": "binance", "size": 1.0, "risk_amount": 5.0,
        "entry_time": 1700000000000, "created_at": "2026-01-01T00:00:00+00:00",
    })
    storage_mod.open_paper_position(pos)
    return pos


def test_signal_message_uses_trade_vision_branding_not_sindhu():
    text = telegram_bot.format_signal_message(_position(), lang="en")
    assert "Trade Vision Signal" in text
    assert "SINDHU" not in text


def test_close_followup_message_uses_trade_vision_branding():
    closed = _position(exit_price=105.0, exit_reason="take_profit", pnl=5.0, pnl_pct=5.0)
    text = (
        f"<b>{telegram_bot.TELEGRAM_BRAND} Result -- WIN</b>\n"
        f"Strategy: {closed['strategy_name']}\n"
    )
    assert "Trade Vision Result" in text
    assert "SINDHU" not in text


def test_test_message_uses_trade_vision_branding():
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        telegram_bot.send_test_message()
    sent_text = mock_send.call_args[0][0]
    assert "Trade Vision test message" in sent_text
    assert "SINDHU" not in sent_text


def test_signal_message_includes_real_statistical_confidence_when_reliable():
    reliability = pattern_stats.classify(wins=20, n=25)
    text = telegram_bot.format_signal_message(_position(), confluence_result=None, reliability_result=reliability, lang="en")
    assert "Statistical Confidence" in text
    assert "80%" in text
    assert "25 recorded trades" in text


def test_signal_message_omits_statistical_confidence_when_insufficient_data():
    reliability = pattern_stats.classify(wins=2, n=3)
    text = telegram_bot.format_signal_message(_position(), confluence_result=None, reliability_result=reliability)
    assert "Statistical Confidence" not in text


def test_auto_send_blocked_when_pattern_not_statistically_reliable(test_db):
    # min_confluence_count=1: this test isolates the Wilson-gate check,
    # not Batch 6 Task 3's minimum-count tightening (see
    # tests/test_confluence_min_count.py for that).
    telegram_bot.save_settings(
        bot_token="dummy", channel_id="123", auto_send_enabled=True,
        auto_send_min_confluence_ratio=0.0, auto_send_min_confluence_count=1,
    )
    _open_position(storage)
    # No pattern memory recorded at all yet -- 0 trades for this exact pattern.
    should_send, reason = telegram_bot.evaluate_auto_send("pos1")
    assert should_send is False
    assert "statistically confident" in reason


def test_pattern_reliability_helper_degrades_gracefully_with_no_history():
    result = telegram_bot._pattern_reliability_for("strat_never_traded", "XYZUSDT", "ranging", "asian")
    assert result["status"] == "insufficient_data"
    assert result["reliable"] is False
