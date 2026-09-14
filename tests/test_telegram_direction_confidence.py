"""2026-09-14 fix: format_signal_message() restores Direction and
Confidence to the Telegram signal message (Grand Master Batch, Phase 2.4
had removed both). Direction is position["direction"] itself, printed
upper-cased. Confidence is position["confidence"] -- the exact value
paper_trading.confidence.score() computed for this signal at open time --
printed verbatim, never rounded/adjusted further and never fabricated
when missing.
"""

from data_engine import config as base_config
from paper_trading import telegram_bot


def _position(**overrides):
    base = {
        "id": "pos1", "strategy_id": "strat1", "strategy_name": "Test Strategy",
        "symbol": "BTCUSDT", "direction": "long", "entry_price": 100.0,
        "stop_loss": 95.0, "take_profit": 110.0, "market_state": "trending_up",
        "session": "london", "entry_reason": "test",
    }
    base.update(overrides)
    return base


def test_direction_is_shown_uppercased_for_long():
    text = telegram_bot.format_signal_message(_position(direction="long"), lang="en")
    assert "Direction: LONG" in text


def test_direction_is_shown_uppercased_for_short():
    text = telegram_bot.format_signal_message(_position(direction="short"), lang="en")
    assert "Direction: SHORT" in text


def test_missing_direction_shows_placeholder_not_a_crash():
    text = telegram_bot.format_signal_message(_position(direction=None), lang="en")
    assert "Direction: --" in text


def test_confidence_is_shown_verbatim_not_rounded_or_adjusted():
    # The real, already-computed value from confidence.score() -- must
    # appear exactly as stored, not rounded to a whole number or bucketed.
    text = telegram_bot.format_signal_message(_position(confidence=61.73), lang="en")
    assert "Confidence: 61.73%" in text


def test_confidence_whole_number_has_no_trailing_decimal_noise():
    text = telegram_bot.format_signal_message(_position(confidence=62.0), lang="en")
    assert "Confidence: 62%" in text


def test_confidence_line_omitted_when_not_present():
    text = telegram_bot.format_signal_message(_position(), lang="en")
    assert "Confidence" not in text


def test_direction_and_confidence_identical_across_languages():
    pos = _position(direction="short", confidence=48.2)
    ur_text = telegram_bot.format_signal_message(pos, lang="ur")
    en_text = telegram_bot.format_signal_message(pos, lang="en")
    assert ur_text == en_text
    assert "Direction: SHORT" in ur_text
    assert "Confidence: 48.2%" in ur_text
