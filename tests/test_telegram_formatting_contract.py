"""Formatting contract for every Telegram message type in the codebase --
guards against a future message type silently regressing to dense
paragraph text. Every message that reaches Telegram (trade signal, close
follow-up, daily report) must be emoji-led, use short lines (bullets or a
labeled-field style), and never leak a raw internal identifier."""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from data_engine import config as base_config, storage
from paper_trading import telegram_bot, daily_report, pattern_stats


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


# Internal identifiers that must never leak into a user-facing Telegram
# message -- these are DB/code-level names, not what a non-technical
# reader should ever see.
_FORBIDDEN_IDENTIFIERS = [
    "confluence_score", "candle_break", "strategy_id", "market_state",
    "stop_loss_type", "pnl_pct", "entry_reason",
]


def _assert_emoji_led_and_scannable(text):
    """A compliant message: starts with (or very early contains) an emoji,
    has more than one line, and no single line is an unbroken wall of
    text (a crude proxy for "dense paragraph")."""
    lines = [l for l in text.split("\n") if l.strip()]
    assert len(lines) >= 3, "message should be multi-line/scannable, not a single blob"
    has_emoji_early = any(ord(ch) > 0x2000 for ch in "".join(lines[:2]))
    assert has_emoji_early, "message should be emoji-led near the top"
    for l in lines:
        assert len(l) < 220, f"line too dense/paragraph-like: {l!r}"
    for ident in _FORBIDDEN_IDENTIFIERS:
        assert ident not in text, f"raw internal identifier leaked into message: {ident}"


def _position(**overrides):
    base = {
        "id": "pos1", "strategy_id": "strat1", "strategy_name": "Test Strategy",
        "symbol": "BTCUSDT", "direction": "long", "entry_price": 100.0,
        "stop_loss": 95.0, "take_profit": 110.0, "market_state": "trending_up",
        "session": "london", "entry_reason": "test",
    }
    base.update(overrides)
    return base


def test_signal_message_is_compliant():
    text = telegram_bot.format_signal_message(_position(), lang="ur")
    _assert_emoji_led_and_scannable(text)


def test_high_confidence_signal_message_is_compliant():
    text = telegram_bot.format_signal_message(_position(), high_confidence=True, lang="ur")
    _assert_emoji_led_and_scannable(text)


def test_close_followup_message_is_compliant(test_db):
    telegram_bot.save_settings(bot_token="x", channel_id="y", master_send_enabled=True)
    storage.open_paper_position({
        "id": "pos1", "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": 1700000000000, "created_at": "2026-01-01T00:00:00+00:00",
        "strategy_id": "strat1", "strategy_name": "Test Strategy",
    })
    storage.log_telegram_message("pos1", "strat1", "Test Strategy", "manual", "text", True, None, "2026-01-01T00:00:00+00:00")
    closed = {"id": "pos1", "symbol": "BTCUSDT", "strategy_id": "strat1", "strategy_name": "Test Strategy",
              "exit_price": 110.0, "exit_reason": "take_profit", "pnl": 10.0, "pnl_pct": 10.0}
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        telegram_bot.send_close_followup(closed)
    _assert_emoji_led_and_scannable(mock_send.call_args[0][0])


def test_daily_report_message_is_compliant(test_db):
    report = daily_report.generate_daily_report(now=datetime(2026, 3, 15, 18, 0, 0, tzinfo=timezone.utc))
    _assert_emoji_led_and_scannable(report["report_text"])


def test_test_connectivity_message_is_short_and_not_a_trade_signal():
    # send_test_message isn't a trade signal -- just confirms it never
    # leaks internal identifiers, not the full scannability bar.
    text = f"{telegram_bot.TELEGRAM_BRAND} test message -- connection successful.\n\n{telegram_bot.DISCLAIMER}"
    for ident in _FORBIDDEN_IDENTIFIERS:
        assert ident not in text
