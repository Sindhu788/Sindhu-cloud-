"""Task 4 (Priority Batch 1) -- dual-tier Telegram signal sending.

HIGH tier = evaluate_auto_send() (unchanged: full confluence + the real
25-trade Wilson gate from paper_trading.pattern_stats) with a distinct
"High Confidence" marker on the sent message. LOW tier = a new fallback
that shares every other safety check but doesn't require the pattern to
already be statistically confirmed, so signal flow doesn't stop entirely
just because nothing currently clears the high bar. Neither tier ever
fabricates a label -- both only ever describe real, already-computed
confluence/statistical data.
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


FULL_CONFLUENCE = {"passed": 4, "total": 4, "label": "Strong -- 4/4 factors aligned", "factors": []}


def _enable_auto_send(min_ratio=1.0):
    telegram_bot.save_settings(
        bot_token="dummy", channel_id="123", auto_send_enabled=True,
        auto_send_min_confluence_ratio=min_ratio,
    )


def test_high_tier_still_requires_the_unchanged_25_trade_wilson_gate(test_db):
    """evaluate_auto_send() (the HIGH tier) is completely untouched by
    Task 4 -- still blocked with no pattern history, exactly as before."""
    _enable_auto_send(min_ratio=0.0)
    _open_position(storage)
    should_send, reason = telegram_bot.evaluate_auto_send("pos1")
    assert should_send is False
    assert "statistically confident" in reason


def test_low_tier_sends_when_high_tier_lacks_statistical_history(test_db):
    """The core Task 4 behavior: full confluence but not yet enough trade
    history for the Wilson gate -- HIGH tier correctly refuses, LOW tier
    picks it up so signal flow doesn't stop."""
    _enable_auto_send()
    _open_position(storage)
    with patch.object(telegram_bot.confluence_mod, "score_confluence", return_value=FULL_CONFLUENCE):
        should_send_high, _ = telegram_bot.evaluate_auto_send("pos1")
        assert should_send_high is False  # no pattern history yet -- correctly blocked

        should_send_low, low_reason = telegram_bot.evaluate_auto_send_low_tier("pos1")
        assert should_send_low is True
        assert "not yet statistically confirmed" in low_reason

        tier, reason = telegram_bot.evaluate_auto_send_tier("pos1")
        assert tier == "low"


def test_high_tier_wins_over_low_tier_when_both_qualify(test_db):
    """evaluate_auto_send_tier() must prefer HIGH over LOW whenever the
    signal genuinely clears both bars -- never silently downgrades a
    qualifying high-confidence signal to the low tier."""
    _enable_auto_send()
    _open_position(storage)
    good_reliability = pattern_stats.classify(wins=23, n=25)  # 92% -- reliable_good
    assert good_reliability["status"] == "reliable_good"

    with patch.object(telegram_bot.confluence_mod, "score_confluence", return_value=FULL_CONFLUENCE), \
         patch.object(telegram_bot, "_pattern_reliability_for", return_value=good_reliability), \
         patch.object(storage, "get_paper_realized_pnl_total", return_value=50.0):
        tier, reason = telegram_bot.evaluate_auto_send_tier("pos1")
        assert tier == "high"


def test_neither_tier_sends_when_confluence_is_below_the_configured_floor(test_db):
    """A genuinely weak signal (below the configured confluence floor)
    must not send at either tier -- signal flow continuing must never mean
    sending everything regardless of quality."""
    _enable_auto_send(min_ratio=0.75)
    _open_position(storage)
    weak_confluence = {"passed": 1, "total": 4, "label": "Weak -- 1/4 factors aligned", "factors": []}
    with patch.object(telegram_bot.confluence_mod, "score_confluence", return_value=weak_confluence):
        tier, reason = telegram_bot.evaluate_auto_send_tier("pos1")
        assert tier is None
        assert "below the required bar" in reason


def test_low_tier_still_respects_the_master_auto_send_toggle(test_db):
    """auto_send_enabled OFF (the safe default) must block BOTH tiers, not
    just the high one -- Task 4 adds a fallback tier, not a way around the
    existing off-by-default safety switch."""
    telegram_bot.save_settings(bot_token="dummy", channel_id="123", auto_send_enabled=False)
    _open_position(storage)
    should_send_low, reason = telegram_bot.evaluate_auto_send_low_tier("pos1")
    assert should_send_low is False
    assert "turned off" in reason


def test_low_tier_blocks_negative_live_pnl_same_as_high_tier(test_db):
    """The existing negative-PnL circuit breaker isn't bypassed by the new
    lower tier."""
    _enable_auto_send()
    _open_position(storage)
    with patch.object(telegram_bot.confluence_mod, "score_confluence", return_value=FULL_CONFLUENCE), \
         patch.object(storage, "get_paper_realized_pnl_total", return_value=-25.0):
        should_send, reason = telegram_bot.evaluate_auto_send_low_tier("pos1")
        assert should_send is False
        assert "negative" in reason


def test_high_confidence_message_has_a_distinct_visible_marker():
    text_high = telegram_bot.format_signal_message(_position(), high_confidence=True)
    text_normal = telegram_bot.format_signal_message(_position(), high_confidence=False)
    assert "HIGH CONFIDENCE SIGNAL" in text_high
    assert "HIGH CONFIDENCE SIGNAL" not in text_normal


def test_send_signal_for_position_passes_high_confidence_marker_through(test_db):
    telegram_bot.save_settings(bot_token="dummy", channel_id="123")
    _open_position(storage)
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        telegram_bot.send_signal_for_position("pos1", trigger_type="automatic", high_confidence=True)
    sent_text = mock_send.call_args[0][0]
    assert "HIGH CONFIDENCE SIGNAL" in sent_text


def test_send_signal_for_position_manual_never_shows_high_confidence_by_default(test_db):
    telegram_bot.save_settings(bot_token="dummy", channel_id="123")
    _open_position(storage)
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        telegram_bot.send_signal_for_position("pos1", trigger_type="manual")
    sent_text = mock_send.call_args[0][0]
    assert "HIGH CONFIDENCE SIGNAL" not in sent_text
