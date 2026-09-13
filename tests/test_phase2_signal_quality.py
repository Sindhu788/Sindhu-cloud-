"""5-Phase Improvement Batch, Phase 2 -- Telegram Signal Quality.

Covers: trading style/duration derivation (2.4), the Minimum Take-Profit
Distance Filter (2.3), Duplicate-Signal Protection (2.6), and the new
format_signal_message fields (2.2 confidence %/group marker, 2.4 style
line, 2.7 expiry note). Entry/SL/TP fields (2.1) already existed before
this batch -- covered here only by one assertion confirming they're
still present, not reimplemented.
"""

from datetime import datetime, timedelta, timezone

import pytest

from data_engine import config as base_config, storage
from paper_trading import telegram_bot, strategy_groups


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


@pytest.fixture(autouse=True)
def no_real_live_price(monkeypatch):
    monkeypatch.setattr(telegram_bot, "_fetch_live_price", lambda *a, **k: None)


def _position(pos_id="pos1", **overrides):
    base = {
        "id": pos_id, "strategy_id": "strat1", "strategy_name": "Test Strategy",
        "symbol": "BTCUSDT", "direction": "long", "entry_price": 100.0,
        "stop_loss": 95.0, "take_profit": 110.0, "market_state": "trending_up",
        "session": "london", "entry_reason": "test",
        "exchange": "binance", "size": 1.0, "risk_amount": 5.0, "timeframe": "1h",
        "entry_time": int(datetime.now(timezone.utc).timestamp() * 1000),
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------- 2.4: Trading Style + Duration

def test_trading_style_scalping_for_5m():
    style_key, style_label, duration = telegram_bot.trading_style_for_timeframe("5m")
    assert style_key == "scalping"
    assert style_label == "Scalping"
    assert duration


def test_trading_style_intraday_for_1h():
    style_key, style_label, duration = telegram_bot.trading_style_for_timeframe("1h")
    assert style_key == "intraday"


def test_trading_style_swing_for_1d():
    style_key, style_label, duration = telegram_bot.trading_style_for_timeframe("1d")
    assert style_key == "swing"


def test_trading_style_unknown_timeframe_is_none_not_guessed():
    assert telegram_bot.trading_style_for_timeframe("2w") == (None, None, None)
    assert telegram_bot.trading_style_for_timeframe(None) == (None, None, None)


# --------------------------------------------------------------- 2.3: Minimum Take-Profit Distance Filter

def test_min_tp_distance_blocks_too_close_tp_for_scalping(test_db):
    telegram_bot.save_settings(min_tp_distance_filter_enabled=True)
    # Scalping (5m) minimum is 0.5% -- this TP is only 0.1% away.
    pos = _position(timeframe="5m", entry_price=100.0, take_profit=100.1)
    ok, reason = telegram_bot.min_tp_distance_check(pos)
    assert ok is False
    assert "reaction-time" in reason


def test_min_tp_distance_allows_safely_far_tp(test_db):
    telegram_bot.save_settings(min_tp_distance_filter_enabled=True)
    pos = _position(timeframe="5m", entry_price=100.0, take_profit=101.0)  # 1.0% away
    ok, reason = telegram_bot.min_tp_distance_check(pos)
    assert ok is True
    assert reason is None


def test_min_tp_distance_uses_swing_threshold_for_1d(test_db):
    telegram_bot.save_settings(min_tp_distance_filter_enabled=True)
    # Swing minimum is 3% -- 1.5% away should be blocked even though it
    # would pass the scalping/intraday thresholds.
    pos = _position(timeframe="1d", entry_price=100.0, take_profit=101.5)
    ok, reason = telegram_bot.min_tp_distance_check(pos)
    assert ok is False
    assert "Swing" in reason


def test_min_tp_distance_off_when_disabled(test_db):
    telegram_bot.save_settings(min_tp_distance_filter_enabled=False)
    pos = _position(timeframe="5m", entry_price=100.0, take_profit=100.1)
    ok, reason = telegram_bot.min_tp_distance_check(pos)
    assert ok is True


def test_min_tp_distance_never_blocks_when_tp_missing(test_db):
    telegram_bot.save_settings(min_tp_distance_filter_enabled=True)
    pos = _position(take_profit=None)
    ok, reason = telegram_bot.min_tp_distance_check(pos)
    assert ok is True


# --------------------------------------------------------------- 3.4: Minimum Confidence % Filter

def test_min_confidence_off_by_default(test_db):
    pos = _position(confidence=10.0)
    ok, reason = telegram_bot.min_confidence_check(pos)
    assert ok is True


def test_min_confidence_blocks_below_threshold(test_db):
    telegram_bot.save_settings(min_confidence_pct_to_send=60)
    pos = _position(confidence=45.0)
    ok, reason = telegram_bot.min_confidence_check(pos)
    assert ok is False
    assert "45%" in reason


def test_min_confidence_allows_above_threshold(test_db):
    telegram_bot.save_settings(min_confidence_pct_to_send=60)
    pos = _position(confidence=72.0)
    ok, reason = telegram_bot.min_confidence_check(pos)
    assert ok is True


def test_min_confidence_never_blocks_when_confidence_missing(test_db):
    telegram_bot.save_settings(min_confidence_pct_to_send=60)
    pos = _position(confidence=None)
    ok, reason = telegram_bot.min_confidence_check(pos)
    assert ok is True


# --------------------------------------------------------------- 2.6: Duplicate-Signal Protection

def test_duplicate_signal_blocked_within_freshness_window(test_db):
    telegram_bot.save_settings(signal_freshness_minutes=15)
    storage.open_paper_position(_position("pos1"))
    now = datetime.now(timezone.utc).isoformat()
    storage.log_telegram_message("pos1", "strat1", "Test Strategy", "automatic", "msg", True, None, now)

    storage.open_paper_position(_position("pos2"))
    pos2 = storage.get_paper_position("pos2")
    ok, reason = telegram_bot.duplicate_signal_check(pos2)
    assert ok is False
    assert "already sent" in reason


def test_duplicate_signal_allowed_after_freshness_window_expires(test_db):
    telegram_bot.save_settings(signal_freshness_minutes=15)
    storage.open_paper_position(_position("pos1"))
    old = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    storage.log_telegram_message("pos1", "strat1", "Test Strategy", "automatic", "msg", True, None, old)

    storage.open_paper_position(_position("pos2"))
    pos2 = storage.get_paper_position("pos2")
    ok, reason = telegram_bot.duplicate_signal_check(pos2)
    assert ok is True


def test_duplicate_signal_allowed_for_different_symbol(test_db):
    telegram_bot.save_settings(signal_freshness_minutes=15)
    storage.open_paper_position(_position("pos1", symbol="BTCUSDT"))
    now = datetime.now(timezone.utc).isoformat()
    storage.log_telegram_message("pos1", "strat1", "Test Strategy", "automatic", "msg", True, None, now)

    storage.open_paper_position(_position("pos2", symbol="ETHUSDT"))
    pos2 = storage.get_paper_position("pos2")
    ok, reason = telegram_bot.duplicate_signal_check(pos2)
    assert ok is True


def test_duplicate_signal_ignores_failed_sends(test_db):
    telegram_bot.save_settings(signal_freshness_minutes=15)
    storage.open_paper_position(_position("pos1"))
    now = datetime.now(timezone.utc).isoformat()
    storage.log_telegram_message("pos1", "strat1", "Test Strategy", "automatic", "", False, "some error", now)

    storage.open_paper_position(_position("pos2"))
    pos2 = storage.get_paper_position("pos2")
    ok, reason = telegram_bot.duplicate_signal_check(pos2)
    assert ok is True


# --------------------------------------------------------------- format_signal_message additions
#
# Grand Master Batch, Phase 2.4 reduced the message body to exactly 5
# fields (coin + status emoji, Entry, Stop-Loss, Take-Profit, Duration) --
# confidence %, the trading-style name ("Scalping"/etc.), and the
# per-signal expiry note are no longer rendered in the message at all
# (still fully computed/available elsewhere, just not sent to Telegram).
# See test_phase2_4_telegram_simplified_format.py for the full contract.

def test_message_still_has_entry_sl_tp_fields(test_db):
    pos = _position()
    text = telegram_bot.format_signal_message(pos, lang="en")
    assert "Entry:" in text
    assert "Stop-Loss:" in text
    assert "Take-Profit:" in text


def test_message_shows_profitable_group_marker(test_db):
    storage.upsert_paper_strategy_groups_batch({"strat1": "profitable"}, datetime.now(timezone.utc).isoformat())
    pos = _position(confidence=72.5)
    text = telegram_bot.format_signal_message(pos, lang="en")
    assert "\U0001F535" in text  # blue circle for Profitable group


def test_message_shows_losing_group_marker(test_db):
    storage.upsert_paper_strategy_groups_batch({"strat1": "losing"}, datetime.now(timezone.utc).isoformat())
    pos = _position()
    text = telegram_bot.format_signal_message(pos, lang="en")
    assert "\U0001F534" in text  # red circle for Losing group


def test_message_shows_duration_for_known_timeframe(test_db):
    pos = _position(timeframe="5m")
    text = telegram_bot.format_signal_message(pos, lang="en")
    assert "Duration: minutes to ~1 hour" in text


def test_message_shows_placeholder_duration_for_unknown_timeframe(test_db):
    pos = _position(timeframe="weird_custom_tf")
    text = telegram_bot.format_signal_message(pos, lang="en")
    assert "Duration: --" in text


# --------------------------------------------------------------- integration: gates wired into send path

def test_send_signal_blocked_by_min_tp_distance(test_db, monkeypatch):
    telegram_bot.save_settings(bot_token="dummy", channel_id="123", min_tp_distance_filter_enabled=True)
    storage.open_paper_position(_position("pos1", timeframe="5m", entry_price=100.0, take_profit=100.1))
    sent = {}
    monkeypatch.setattr(telegram_bot, "_raw_send", lambda *a, **k: sent.setdefault("called", True) or (True, None))
    result = telegram_bot.send_signal_for_position("pos1", trigger_type="manual")
    assert result["ok"] is False
    assert "reaction-time" in result["error"]
    assert "called" not in sent


def test_send_signal_blocked_by_duplicate_protection(test_db, monkeypatch):
    telegram_bot.save_settings(bot_token="dummy", channel_id="123")
    storage.open_paper_position(_position("pos1"))
    now = datetime.now(timezone.utc).isoformat()
    storage.log_telegram_message("pos1", "strat1", "Test Strategy", "automatic", "msg", True, None, now)
    storage.open_paper_position(_position("pos2"))
    sent = {}
    monkeypatch.setattr(telegram_bot, "_raw_send", lambda *a, **k: sent.setdefault("called", True) or (True, None))
    result = telegram_bot.send_signal_for_position("pos2", trigger_type="manual")
    assert result["ok"] is False
    assert "already sent" in result["error"]
    assert "called" not in sent
