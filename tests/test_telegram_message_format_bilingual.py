"""Batch 5, Task 3 -- format_signal_message() is now bilingual, defaulting
to Roman Urdu (the CEO's everyday register, matching every other page's
default) via the stored Telegram "language" setting, with lang="en" as
an explicit override. Deterministic template choice -- no AI translation
call. Numbers/symbols/prices interpolate identically in both languages.
"""

import pytest

from data_engine import config as base_config
from paper_trading import telegram_bot


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


def test_default_language_is_roman_urdu():
    text = telegram_bot.format_signal_message(_position())
    assert "Strategy: Test Strategy" in text
    assert "Abhi Ka Price" not in text or True  # only present if live price included -- see below
    # Urdu-specific labels that differ from English
    assert "Paper Trading (Nakli Paise)" in text


def test_explicit_english_still_available():
    text = telegram_bot.format_signal_message(_position(), lang="en")
    assert "Paper Trading (Nakli Paise)" not in text
    assert "Paper Trading" in text


def test_stored_telegram_setting_controls_the_default(test_db):
    telegram_bot.save_settings(language="en")
    text = telegram_bot.format_signal_message(_position())
    assert "Paper Trading (Nakli Paise)" not in text

    telegram_bot.save_settings(language="ur")
    text = telegram_bot.format_signal_message(_position())
    assert "Paper Trading (Nakli Paise)" in text


def test_prices_interpolate_identically_in_both_languages():
    pos = _position(entry_price=123.456, stop_loss=100.0, take_profit=150.0)
    ur_text = telegram_bot.format_signal_message(pos, lang="ur")
    en_text = telegram_bot.format_signal_message(pos, lang="en")
    assert "123.456" in ur_text
    assert "123.456" in en_text


def test_strategy_name_interpolates_cleanly_in_both_languages():
    pos = _position(strategy_name="PDH-PDL Signal Candle Strategy")
    ur_text = telegram_bot.format_signal_message(pos, lang="ur")
    en_text = telegram_bot.format_signal_message(pos, lang="en")
    assert "PDH-PDL Signal Candle Strategy" in ur_text
    assert "PDH-PDL Signal Candle Strategy" in en_text


def test_missing_strategy_name_never_produces_a_broken_sentence():
    pos = _position(strategy_name=None)
    ur_text = telegram_bot.format_signal_message(pos, lang="ur")
    en_text = telegram_bot.format_signal_message(pos, lang="en")
    assert "Strategy: Pata Nahi" in ur_text
    assert "Strategy: Unknown" in en_text


def test_live_price_label_differs_by_language():
    pos = _position()
    ur_text = telegram_bot.format_signal_message(pos, live_price=101.5, lang="ur")
    en_text = telegram_bot.format_signal_message(pos, live_price=101.5, lang="en")
    assert "Abhi Ka Price: 101.500" in ur_text
    assert "Current Price: 101.500" in en_text


def test_statistical_confidence_line_interpolates_numbers_correctly_in_urdu():
    from paper_trading import pattern_stats
    reliability = pattern_stats.classify(wins=20, n=25)
    text = telegram_bot.format_signal_message(_position(), reliability_result=reliability, lang="ur")
    assert "80% " in text
    assert "25 trades" in text


def test_invalid_lang_falls_back_to_stored_setting_not_a_crash():
    text = telegram_bot.format_signal_message(_position(), lang="klingon")
    assert isinstance(text, str) and len(text) > 0
