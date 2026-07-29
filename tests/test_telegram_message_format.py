"""Tests for Task A (number-formatting fix) and Task B (message redesign)
in paper_trading/telegram_bot.py. Task A is a DISPLAY-ONLY rounding fix --
these tests confirm the message text is cleanly rounded while the
underlying position dict's raw values stay untouched. Task B tests the
new message structure: header, direction, LEVELS section, confidence
section, Why This Trade factors, timestamp/age, footer.
"""

from unittest.mock import patch

from paper_trading import telegram_bot, pattern_stats


def _position(**overrides):
    base = {
        "id": "pos1", "strategy_id": "strat1", "strategy_name": "Test Strategy",
        "symbol": "BTCUSDT", "direction": "long", "entry_price": 100.0,
        "stop_loss": 95.0, "take_profit": 110.0, "market_state": "trending_up",
        "session": "london", "entry_reason": "test",
    }
    base.update(overrides)
    return base


def _confluence(passed=3, total=3, factor_names=None):
    factor_names = factor_names or ["Market condition supports this signal",
                                     "Strategy not paused for safety",
                                     "No existing position already crowding this coin"]
    factors = [{"name": n, "result": True} for n in factor_names[:passed]]
    factors += [{"name": n, "result": False} for n in factor_names[passed:total]]
    strength = "Strong" if total and passed / total >= 0.75 else "Moderate" if total and passed / total >= 0.5 else "Weak"
    label = f"{strength} -- {passed}/{total} factors aligned"
    return {"label": label, "passed": passed, "total": total, "factors": factors}


# --------------------------------------------------------------- Task A: number formatting

def test_long_decimal_tail_is_rounded_for_high_priced_coin():
    pos = _position(entry_price=4.0917436867418004, stop_loss=4.0917436867418004, take_profit=1.5215126265163987)
    text = telegram_bot.format_signal_message(pos)
    assert "4.0917436867418004" not in text
    assert "1.5215126265163987" not in text
    assert "4.092" in text
    assert "1.522" in text


def test_formatting_does_not_mutate_stored_position_values():
    pos = _position(entry_price=4.0917436867418004)
    telegram_bot.format_signal_message(pos)
    assert pos["entry_price"] == 4.0917436867418004  # untouched -- display-only


def test_low_priced_coin_keeps_meaningful_precision():
    # A flat 3-decimal round would display this as "0.000", losing all
    # real information for a genuinely sub-cent coin.
    text = telegram_bot.format_signal_message(_position(entry_price=0.00030912345, stop_loss=0.00029, take_profit=0.00033))
    assert "Entry: 0.000\n" not in text  # not rounded away to a meaningless flat zero
    assert "0.0003091" in text


def test_price_at_least_three_decimals_even_for_expensive_coin():
    text = telegram_bot.format_signal_message(_position(entry_price=50000.1, stop_loss=49000.0, take_profit=52000.0))
    assert "50000.100" in text


def test_format_price_handles_none_and_zero():
    assert telegram_bot._format_price(None) == "-"
    assert telegram_bot._format_price(0) == "0.000"


# --------------------------------------------------------------- Task B: message redesign

def test_message_has_branded_header_and_divider():
    text = telegram_bot.format_signal_message(_position())
    assert "Trade Vision Signal" in text
    assert "─" in text


def test_message_shows_direction_emoji_and_symbol():
    long_text = telegram_bot.format_signal_message(_position(direction="long", symbol="ETHUSDT"))
    short_text = telegram_bot.format_signal_message(_position(direction="short", symbol="ETHUSDT"))
    assert "\U0001F7E2" in long_text and "LONG ETHUSDT" in long_text
    assert "\U0001F534" in short_text and "SHORT ETHUSDT" in short_text


def test_message_has_levels_section_with_warning_and_target_icons():
    text = telegram_bot.format_signal_message(_position())
    assert "LEVELS" in text
    assert "⚠️ Stop-Loss:" in text
    assert "\U0001F3AF Take-Profit:" in text


def test_message_omits_live_price_when_fetch_fails():
    with patch.object(telegram_bot, "_fetch_live_price", return_value=None):
        text = telegram_bot.format_signal_message(_position())
    assert "Current Price" not in text


def test_message_includes_live_price_when_available():
    with patch.object(telegram_bot, "_fetch_live_price", return_value=101.234567):
        text = telegram_bot.format_signal_message(_position())
    assert "Current Price: 101.235" in text


def test_message_shows_qualitative_confidence_with_icon_when_not_statistically_reliable():
    conf = _confluence(passed=3, total=3)
    text = telegram_bot.format_signal_message(_position(), confluence_result=conf)
    assert "\U0001F7E2 Confidence: Strong -- 3/3 factors aligned" in text
    assert "Statistical Confidence" not in text


def test_message_prefers_statistical_confidence_when_reliable():
    conf = _confluence(passed=3, total=3)
    reliability = pattern_stats.classify(wins=20, n=25)
    text = telegram_bot.format_signal_message(_position(), confluence_result=conf, reliability_result=reliability)
    assert "Statistical Confidence: 80% win rate over 25 recorded trades" in text
    assert "\U0001F7E2 Confidence: Strong" not in text  # qualitative line not duplicated


def test_message_lists_why_this_trade_factors_from_real_confluence_data():
    conf = _confluence(passed=2, total=3, factor_names=["Market condition supports this signal", "Strategy not paused for safety", "No existing position already crowding this coin"])
    text = telegram_bot.format_signal_message(_position(), confluence_result=conf)
    assert "Why This Trade" in text
    assert "• Market condition supports this signal" in text
    assert "• Strategy not paused for safety" in text
    assert "No existing position already crowding this coin" not in text  # this factor did not align


def test_message_omits_why_this_trade_when_no_factors_aligned():
    conf = _confluence(passed=0, total=3)
    text = telegram_bot.format_signal_message(_position(), confluence_result=conf)
    assert "Why This Trade" not in text


def test_message_shows_timestamp_and_age():
    import time
    entry_ms = int(time.time() * 1000) - (5 * 60 * 1000)  # 5 minutes ago
    text = telegram_bot.format_signal_message(_position(entry_time=entry_ms))
    assert "UTC" in text
    assert "5m ago" in text


def test_message_footer_has_strategy_source_and_disclaimer():
    text = telegram_bot.format_signal_message(_position())
    assert "Trade Vision -- Paper Trading" in text
    assert telegram_bot.DISCLAIMER in text


def test_signal_age_text_buckets():
    now_ms = telegram_bot.datetime.now(telegram_bot.timezone.utc).timestamp() * 1000
    assert telegram_bot._signal_age_text(now_ms - 30 * 1000) == "just now"
    assert telegram_bot._signal_age_text(now_ms - 5 * 60 * 1000) == "5m ago"
    assert telegram_bot._signal_age_text(now_ms - 2 * 3600 * 1000 - 10 * 60 * 1000) == "2h 10m ago"
    assert telegram_bot._signal_age_text(now_ms - 3 * 86400 * 1000) == "3d ago"
    assert telegram_bot._signal_age_text(None) is None
