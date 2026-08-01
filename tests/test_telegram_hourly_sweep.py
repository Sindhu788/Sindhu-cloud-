"""Batch 2, Task 4 -- the hourly Telegram fresh-signal sweep
(telegram_bot.sweep_unsent_qualifying_signals): a safety net for any open
position that never got a signal sent, re-evaluated through the exact
same dual-tier gating used at open-time (never a looser/bypassed check),
and never re-sent for a position that already has one logged.
"""

from unittest.mock import patch

import pytest

from data_engine import config as base_config, storage
from paper_trading import telegram_bot, pattern_stats


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _position(pos_id="pos1", **overrides):
    base = {
        "id": pos_id, "strategy_id": "strat1", "strategy_name": "Test Strategy",
        "symbol": "BTCUSDT", "direction": "long", "entry_price": 100.0,
        "stop_loss": 95.0, "take_profit": 110.0, "market_state": "trending_up",
        "session": "london", "entry_reason": "test",
        "exchange": "binance", "size": 1.0, "risk_amount": 5.0,
        "entry_time": 1700000000000, "created_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(overrides)
    return base


def _enable_auto_send(min_ratio=1.0):
    telegram_bot.save_settings(bot_token="dummy", channel_id="123", auto_send_enabled=True,
                                auto_send_min_confluence_ratio=min_ratio)


FULL_CONFLUENCE = {"passed": 4, "total": 4, "label": "Strong -- 4/4 factors aligned", "factors": []}


def test_sweep_sends_an_unsent_position_that_now_qualifies(test_db):
    _enable_auto_send()
    storage.open_paper_position(_position("pos1"))
    good_reliability = pattern_stats.classify(wins=23, n=25)

    with patch.object(telegram_bot.confluence_mod, "score_confluence", return_value=FULL_CONFLUENCE), \
         patch.object(telegram_bot, "_pattern_reliability_for", return_value=good_reliability), \
         patch.object(storage, "get_paper_realized_pnl_total", return_value=50.0), \
         patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        sent = telegram_bot.sweep_unsent_qualifying_signals()

    assert len(sent) == 1
    assert sent[0]["position_id"] == "pos1"
    assert sent[0]["tier"] == "high"
    mock_send.assert_called_once()
    assert storage.has_telegram_signal_for_position("pos1") is True


def test_sweep_does_not_resend_a_position_that_already_has_a_signal(test_db):
    _enable_auto_send()
    storage.open_paper_position(_position("pos1"))
    now = "2026-01-01T01:00:00+00:00"
    storage.log_telegram_message("pos1", "strat1", "Test Strategy", "manual", "already sent", True, None, now)

    with patch.object(telegram_bot, "_raw_send") as mock_send:
        sent = telegram_bot.sweep_unsent_qualifying_signals()

    assert sent == []
    mock_send.assert_not_called()


def test_sweep_does_not_send_a_position_that_still_does_not_qualify(test_db):
    """A weak signal (below the configured confluence floor) must not
    send at either tier during the sweep, same as the real-time path."""
    _enable_auto_send(min_ratio=1.0)  # strict default -- require full confluence
    storage.open_paper_position(_position("pos1"))
    weak_confluence = {"passed": 1, "total": 4, "label": "Weak -- 1/4 factors aligned", "factors": []}

    with patch.object(telegram_bot.confluence_mod, "score_confluence", return_value=weak_confluence), \
         patch.object(telegram_bot, "_raw_send") as mock_send:
        sent = telegram_bot.sweep_unsent_qualifying_signals()

    assert sent == []
    mock_send.assert_not_called()


def test_sweep_does_nothing_when_auto_send_is_off(test_db):
    telegram_bot.save_settings(bot_token="dummy", channel_id="123", auto_send_enabled=False)
    storage.open_paper_position(_position("pos1"))
    with patch.object(telegram_bot, "_raw_send") as mock_send:
        sent = telegram_bot.sweep_unsent_qualifying_signals()
    assert sent == []
    mock_send.assert_not_called()


def test_sweep_only_sends_low_tier_when_high_does_not_qualify(test_db):
    _enable_auto_send()
    storage.open_paper_position(_position("pos1"))

    with patch.object(telegram_bot.confluence_mod, "score_confluence", return_value=FULL_CONFLUENCE), \
         patch.object(storage, "get_paper_realized_pnl_total", return_value=10.0), \
         patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        # no reliability data mocked -- real _pattern_reliability_for returns
        # insufficient_data, so High refuses but Low (no Wilson requirement) picks it up
        sent = telegram_bot.sweep_unsent_qualifying_signals()

    assert len(sent) == 1
    assert sent[0]["tier"] == "low"
    sent_text = mock_send.call_args[0][0]
    assert "HIGH CONFIDENCE SIGNAL" not in sent_text


def test_sweep_handles_multiple_open_positions_independently(test_db):
    _enable_auto_send(min_ratio=0.0)
    storage.open_paper_position(_position("pos1"))
    storage.open_paper_position(_position("pos2", symbol="ETHUSDT"))
    # pos2 already has a signal -- must be skipped, pos1 must still be considered
    storage.log_telegram_message("pos2", "strat1", "Test Strategy", "manual", "sent", True, None, "2026-01-01T00:00:00+00:00")

    with patch.object(telegram_bot.confluence_mod, "score_confluence", return_value=FULL_CONFLUENCE), \
         patch.object(storage, "get_paper_realized_pnl_total", return_value=10.0), \
         patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        sent = telegram_bot.sweep_unsent_qualifying_signals()

    position_ids_sent = [s["position_id"] for s in sent]
    assert "pos2" not in position_ids_sent  # already had a signal -- never touched
    assert mock_send.call_count == len(sent)
