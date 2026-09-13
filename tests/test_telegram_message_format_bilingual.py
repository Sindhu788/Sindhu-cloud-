"""Batch 5, Task 3 made format_signal_message() bilingual (Roman Urdu
default / English override). Grand Master Batch, Phase 2.4 then reduced
the message body to exactly 5 fields (coin + status emoji, Entry,
Stop-Loss, Take-Profit, Duration) -- every field that USED to differ by
language (Strategy name line, live price label, statistical confidence
sentence, footer brand) was removed from the message entirely. The
"entry"/"stop_loss"/"take_profit"/"duration" labels that remain are
already identical strings in both _LABELS["ur"] and _LABELS["en"], so
lang now has no observable effect on this function's output -- these
tests confirm that explicitly, plus that an invalid lang still never
crashes. See test_phase2_4_telegram_simplified_format.py for the current
5-field contract itself.
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


def test_ur_and_en_produce_identical_text_for_the_simplified_message():
    pos = _position()
    assert telegram_bot.format_signal_message(pos, lang="ur") == telegram_bot.format_signal_message(pos, lang="en")


def test_prices_interpolate_identically_in_both_languages():
    pos = _position(entry_price=123.456, stop_loss=100.0, take_profit=150.0)
    ur_text = telegram_bot.format_signal_message(pos, lang="ur")
    en_text = telegram_bot.format_signal_message(pos, lang="en")
    assert "123.456" in ur_text
    assert "123.456" in en_text


def test_invalid_lang_falls_back_to_stored_setting_not_a_crash():
    text = telegram_bot.format_signal_message(_position(), lang="klingon")
    assert isinstance(text, str) and len(text) > 0
