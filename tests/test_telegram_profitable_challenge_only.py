"""Urgent CEO directive, 2026-09-15: Telegram signal SENDING is restricted
to strategies currently in the Profitable or Challenge group. Losing-group
strategies keep paper trading exactly as before (this gate never touches
strategy_groups' classification logic, risk_manager, or the tick loop) --
their signals are just never sent to Telegram, so their data keeps
accumulating for later re-evaluation.

This is a NEW, always-on gate, separate from the existing
Group-Selection Mode channel-routing filter (group_filter_check /
channel_group_filter, which only ever changes WHICH channel a signal goes
to and defaults to "all" = no filtering, see
test_phase6_group_selection.py) and from every other existing gate
(confidence, Wilson/confluence tier, Freshness) -- purely additive.
"""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from data_engine import config as base_config, storage
from paper_trading import telegram_bot


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


@pytest.fixture(autouse=True)
def no_real_live_price(monkeypatch):
    monkeypatch.setattr(telegram_bot, "_fetch_live_price", lambda *a, **k: None)


def _open_position(strategy_id="strat1", position_id="pos1"):
    pos = {
        "id": position_id, "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": int(datetime.now(timezone.utc).timestamp() * 1000),
        "created_at": "2026-01-01T00:00:00+00:00",
        "strategy_id": strategy_id, "strategy_name": "Test Strategy",
        "stop_loss": 95.0, "take_profit": 110.0,
    }
    storage.open_paper_position(pos)
    return pos


def _assign_group(strategy_id, group_key):
    storage.upsert_paper_strategy_groups_batch({strategy_id: group_key}, datetime.now(timezone.utc).isoformat())


def test_profitable_group_signal_is_sent(test_db):
    _open_position()
    _assign_group("strat1", "profitable")
    telegram_bot.save_settings(bot_token="dummy", channel_id="123")
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        result = telegram_bot.send_signal_for_position("pos1", trigger_type="manual")
    assert result["ok"] is True
    mock_send.assert_called()


def test_challenge_group_signal_is_sent(test_db):
    _open_position()
    _assign_group("strat1", "challenge")
    telegram_bot.save_settings(bot_token="dummy", channel_id="123")
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        result = telegram_bot.send_signal_for_position("pos1", trigger_type="manual")
    assert result["ok"] is True
    mock_send.assert_called()


def test_losing_group_signal_is_blocked(test_db):
    _open_position()
    _assign_group("strat1", "losing")
    telegram_bot.save_settings(bot_token="dummy", channel_id="123")
    with patch("requests.post") as mock_post:
        result = telegram_bot.send_signal_for_position("pos1", trigger_type="manual")
    assert result["ok"] is False
    assert "Losing group" in result["error"]
    mock_post.assert_not_called()


def test_unclassified_strategy_is_still_sent(test_db):
    """Real evidence from this session: an earlier version of this gate
    blocked unclassified strategies too, which broke 31 existing tests --
    a great many pre-existing tests open a position for a strategy that
    was never assigned a group. Only the Losing group is explicitly named
    by the CEO's directive, so "not yet classified" is left alone,
    unaffected by this new gate."""
    _open_position()
    telegram_bot.save_settings(bot_token="dummy", channel_id="123")
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        result = telegram_bot.send_signal_for_position("pos1", trigger_type="manual")
    assert result["ok"] is True
    mock_send.assert_called()


def test_losing_group_rejection_is_still_logged_to_the_audit_trail(test_db):
    """The strategy keeps trading and its rejection is fully auditable --
    nothing is silently dropped, same "every gate has a visible reason"
    convention every other gate in this file follows."""
    _open_position()
    _assign_group("strat1", "losing")
    telegram_bot.save_settings(bot_token="dummy", channel_id="123")
    with patch("requests.post"):
        telegram_bot.send_signal_for_position("pos1", trigger_type="manual")
    log = storage.list_telegram_messages(limit=10)
    assert any(row["position_id"] == "pos1" and not row["success"] and "Losing group" in (row["error"] or "") for row in log)


def test_gate_runs_before_the_confidence_and_freshness_gates(test_db):
    """A losing-group strategy is rejected by THIS gate even when it would
    also fail later gates for an unrelated reason -- proves this runs
    early in the chain, not dependent on surviving confidence/freshness
    first (Phase 8 verification's own cheap-gates-first ordering)."""
    pos = _open_position()
    _assign_group("strat1", "losing")
    telegram_bot.save_settings(bot_token="dummy", channel_id="123", min_confidence_pct=99)
    with patch("requests.post") as mock_post, patch.object(telegram_bot, "freshness_check") as mock_fresh:
        result = telegram_bot.send_signal_for_position("pos1", trigger_type="manual")
    assert result["ok"] is False
    assert "Losing group" in result["error"]
    mock_fresh.assert_not_called()
    mock_post.assert_not_called()


def test_a_profitable_strategy_still_respects_the_existing_group_selection_channel_filter(test_db):
    """This new gate is purely additive -- the pre-existing
    Group-Selection Mode channel-routing filter (group_filter_check) still
    applies on top of it for a strategy that passes this new gate."""
    _open_position()
    _assign_group("strat1", "profitable")
    telegram_bot.save_settings(bot_token="dummy", channel_id="123", channel_group_filter="challenge")
    with patch("requests.post") as mock_post:
        result = telegram_bot.send_signal_for_position("pos1", trigger_type="manual")
    assert result["ok"] is False
    assert "channel is filtered" in result["error"]
    mock_post.assert_not_called()
