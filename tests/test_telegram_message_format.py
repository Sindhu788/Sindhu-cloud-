"""Tests for Task A (number-formatting fix) in paper_trading/telegram_bot.py.
Task A is a DISPLAY-ONLY rounding fix -- these tests confirm the message
text is cleanly rounded while the underlying position dict's raw values
stay untouched.

The old "Task B" section here tested the pre-Phase-2.4 message design
(header/direction emoji/LEVELS section/confidence/Why This Trade/
timestamp/footer) -- all removed by the Grand Master Batch, Phase 2.4
simplification (message body is now exactly 5 fields: coin + status
emoji, Entry, Stop-Loss, Take-Profit, Duration). See
test_phase2_4_telegram_simplified_format.py for the current contract.

All calls here pass lang="en" explicitly -- Batch 5, Task 3 made
format_signal_message() bilingual and changed the default to "ur" (the
CEO's everyday register, matching every other page's default), so this
file deliberately locks itself to the English variant it was written to
test. See test_telegram_message_format_bilingual.py for the Roman Urdu
variant and the language-selection behavior itself.
"""

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


# --------------------------------------------------------------- Task A: number formatting

def test_long_decimal_tail_is_rounded_for_high_priced_coin():
    pos = _position(entry_price=4.0917436867418004, stop_loss=4.0917436867418004, take_profit=1.5215126265163987)
    text = telegram_bot.format_signal_message(pos, lang="en")
    assert "4.0917436867418004" not in text
    assert "1.5215126265163987" not in text
    assert "4.092" in text
    assert "1.522" in text


def test_formatting_does_not_mutate_stored_position_values():
    pos = _position(entry_price=4.0917436867418004)
    telegram_bot.format_signal_message(pos, lang="en")
    assert pos["entry_price"] == 4.0917436867418004  # untouched -- display-only


def test_low_priced_coin_keeps_meaningful_precision():
    # A flat 3-decimal round would display this as "0.000", losing all
    # real information for a genuinely sub-cent coin.
    pos = _position(entry_price=0.00030912345, stop_loss=0.00029, take_profit=0.00033)
    text = telegram_bot.format_signal_message(pos, lang="en")
    assert "Entry: 0.000\n" not in text  # not rounded away to a meaningless flat zero
    assert "0.0003091" in text


def test_price_at_least_three_decimals_even_for_expensive_coin():
    pos = _position(entry_price=50000.1, stop_loss=49000.0, take_profit=52000.0)
    text = telegram_bot.format_signal_message(pos, lang="en")
    assert "50000.100" in text


def test_format_price_handles_none_and_zero():
    assert telegram_bot._format_price(None) == "-"
    assert telegram_bot._format_price(0) == "0.000"


