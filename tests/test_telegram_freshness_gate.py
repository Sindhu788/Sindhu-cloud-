"""Batch 3, Task 4 (Part B) -- the Signal Freshness Gate. A signal that's
too old, or whose live price has already moved away from the intended
entry, is withheld rather than sent as a normal signal -- because by the
time a stale signal reaches Telegram, the opportunity it describes is
likely already gone. Reconciled with Batch 2's hourly sweep by
construction: both paths go through the same send_signal_for_position(),
so the sweep can never resurrect and send a signal this gate would
refuse.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from data_engine import config as base_config, storage
from paper_trading import telegram_bot


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _now_ms():
    return datetime.now(timezone.utc).timestamp() * 1000


def _position(entry_time_ms, entry_price=100.0, pos_id="pos1", **overrides):
    base = {
        "id": pos_id, "strategy_id": "strat1", "strategy_name": "Test Strategy",
        "symbol": "BTCUSDT", "direction": "long", "entry_price": entry_price,
        "stop_loss": 95.0, "take_profit": 110.0, "market_state": "trending_up",
        "session": "london", "entry_reason": "test",
        "exchange": "binance", "size": 1.0, "risk_amount": 5.0,
        "entry_time": int(entry_time_ms), "created_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(overrides)
    return base


# ------------------------------------------------------------ signal_age_minutes / is_signal_stale

def test_signal_age_minutes_computes_real_elapsed_time():
    now = _now_ms()
    pos = _position(entry_time_ms=now - 5 * 60_000)  # 5 minutes ago
    age = telegram_bot.signal_age_minutes(pos, now_ms=now)
    assert 4.9 <= age <= 5.1


def test_signal_age_minutes_returns_none_when_entry_time_missing():
    pos = _position(entry_time_ms=_now_ms())
    pos["entry_time"] = None
    assert telegram_bot.signal_age_minutes(pos) is None


def test_is_signal_stale_false_within_the_freshness_window():
    now = _now_ms()
    pos = _position(entry_time_ms=now - 10 * 60_000)  # 10 minutes ago
    assert telegram_bot.is_signal_stale(pos, now_ms=now, max_age_minutes=15) is False


def test_is_signal_stale_true_past_the_freshness_window():
    now = _now_ms()
    pos = _position(entry_time_ms=now - 20 * 60_000)  # 20 minutes ago
    assert telegram_bot.is_signal_stale(pos, now_ms=now, max_age_minutes=15) is True


def test_is_signal_stale_respects_configured_setting_not_just_the_default():
    telegram_bot.save_settings(signal_freshness_minutes=5)
    now = _now_ms()
    pos = _position(entry_time_ms=now - 7 * 60_000)  # 7 minutes ago -- stale at a 5-min window
    assert telegram_bot.is_signal_stale(pos, now_ms=now) is True


# ------------------------------------------------------------ price_has_moved_away

def test_price_has_moved_away_false_when_price_is_close_to_entry():
    pos = _position(entry_time_ms=_now_ms(), entry_price=100.0)
    assert telegram_bot.price_has_moved_away(pos, live_price=100.2, max_drift_pct=0.5) is False


def test_price_has_moved_away_true_when_price_moved_beyond_threshold():
    pos = _position(entry_time_ms=_now_ms(), entry_price=100.0)
    assert telegram_bot.price_has_moved_away(pos, live_price=102.0, max_drift_pct=0.5) is True


def test_price_has_moved_away_checks_both_directions():
    pos = _position(entry_time_ms=_now_ms(), entry_price=100.0)
    assert telegram_bot.price_has_moved_away(pos, live_price=98.0, max_drift_pct=0.5) is True


def test_price_has_moved_away_never_blocks_when_live_price_unavailable():
    pos = _position(entry_time_ms=_now_ms(), entry_price=100.0)
    assert telegram_bot.price_has_moved_away(pos, live_price=None) is False


# ------------------------------------------------------------ send_signal_for_position: the 3 required cases

def test_case_1_fresh_signal_sends_normally(test_db):
    """Case 1: a fresh signal with price still near the entry sends normally."""
    telegram_bot.save_settings(bot_token="dummy", channel_id="123")
    pos = _position(entry_time_ms=_now_ms() - 2 * 60_000, entry_price=100.0)  # 2 minutes old
    storage.open_paper_position(pos)

    with patch.object(telegram_bot, "_fetch_live_price", return_value=100.1), \
         patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        result = telegram_bot.send_signal_for_position("pos1", trigger_type="manual")

    assert result["ok"] is True
    mock_send.assert_called_once()
    sent_text = mock_send.call_args[0][0]
    assert "Current Price: 100.1" in sent_text or "100.100" in sent_text  # live price shown
    assert "just now" in sent_text or "m ago" in sent_text  # age shown


def test_case_2_stale_signal_is_withheld(test_db):
    """Case 2: a signal older than the freshness window is never sent."""
    telegram_bot.save_settings(bot_token="dummy", channel_id="123", signal_freshness_minutes=15)
    pos = _position(entry_time_ms=_now_ms() - 30 * 60_000, entry_price=100.0)  # 30 minutes old
    storage.open_paper_position(pos)

    with patch.object(telegram_bot, "_fetch_live_price", return_value=100.0), \
         patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        result = telegram_bot.send_signal_for_position("pos1", trigger_type="manual")

    assert result["ok"] is False
    assert "stale" in result["error"] or "old" in result["error"]
    mock_send.assert_not_called()
    logged = storage.list_telegram_messages(limit=1)[0]
    assert logged["success"] == 0


def test_case_3_price_moved_away_is_withheld(test_db):
    """Case 3: a fresh signal whose live price has already run away from
    the intended entry is never sent."""
    telegram_bot.save_settings(bot_token="dummy", channel_id="123", signal_price_drift_pct=0.5)
    pos = _position(entry_time_ms=_now_ms() - 1 * 60_000, entry_price=100.0)  # fresh, 1 minute old
    storage.open_paper_position(pos)

    with patch.object(telegram_bot, "_fetch_live_price", return_value=103.0), \
         patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        result = telegram_bot.send_signal_for_position("pos1", trigger_type="manual")

    assert result["ok"] is False
    assert "moved" in result["error"]
    mock_send.assert_not_called()


# ------------------------------------------------------------ reconciliation with the Batch 2 hourly sweep

def test_hourly_sweep_never_resurrects_a_stale_signal(test_db):
    """The sweep (Batch 2, Task 4) must never send a signal this gate
    would refuse -- proven structurally here since both paths share
    send_signal_for_position(), not by re-implementing the check."""
    telegram_bot.save_settings(bot_token="dummy", channel_id="123", auto_send_enabled=True,
                                auto_send_min_confluence_ratio=0.0, signal_freshness_minutes=15)
    pos = _position(entry_time_ms=_now_ms() - 60 * 60_000, entry_price=100.0)  # 1 hour old -- stale
    storage.open_paper_position(pos)

    full_confluence = {"passed": 4, "total": 4, "label": "Strong -- 4/4 factors aligned", "factors": []}
    with patch.object(telegram_bot.confluence_mod, "score_confluence", return_value=full_confluence), \
         patch.object(storage, "get_paper_realized_pnl_total", return_value=10.0), \
         patch.object(telegram_bot, "_fetch_live_price", return_value=100.0), \
         patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        sent = telegram_bot.sweep_unsent_qualifying_signals()

    assert sent == []
    mock_send.assert_not_called()


def test_hourly_sweep_still_sends_a_fresh_qualifying_signal(test_db):
    """The freshness gate must not accidentally break the sweep's real
    job -- a genuinely fresh, qualifying signal still goes out."""
    telegram_bot.save_settings(bot_token="dummy", channel_id="123", auto_send_enabled=True,
                                auto_send_min_confluence_ratio=0.0, signal_freshness_minutes=15)
    pos = _position(entry_time_ms=_now_ms() - 2 * 60_000, entry_price=100.0)  # fresh
    storage.open_paper_position(pos)

    full_confluence = {"passed": 4, "total": 4, "label": "Strong -- 4/4 factors aligned", "factors": []}
    with patch.object(telegram_bot.confluence_mod, "score_confluence", return_value=full_confluence), \
         patch.object(storage, "get_paper_realized_pnl_total", return_value=10.0), \
         patch.object(telegram_bot, "_fetch_live_price", return_value=100.1), \
         patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        sent = telegram_bot.sweep_unsent_qualifying_signals()

    assert len(sent) == 1
    mock_send.assert_called_once()
