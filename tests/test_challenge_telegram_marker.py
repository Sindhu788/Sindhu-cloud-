"""CEO Task 3 -- Independent Paper Trading Groups: every Telegram SIGNAL
sent for a Group C ("Challenge") strategy must end with the exact marker
",,,teen,,," so it's instantly visually distinguishable from a normal
Group A/B signal -- and ONLY Group C signals get it.
"""
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from data_engine import config as base_config, storage
from paper_trading import strategy_groups, telegram_bot


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


@pytest.fixture(autouse=True)
def no_real_live_price(monkeypatch):
    monkeypatch.setattr(telegram_bot, "_fetch_live_price", lambda *a, **k: None)


def _open_position(strategy_id, **overrides):
    pos = {
        "id": f"pos-{strategy_id}", "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": int(datetime.now(timezone.utc).timestamp() * 1000),
        "created_at": "2026-01-01T00:00:00+00:00",
        "strategy_id": strategy_id, "strategy_name": "Test Strategy",
    }
    pos.update(overrides)
    storage.open_paper_position(pos)
    return pos


def test_challenge_group_signal_ends_with_marker(test_db):
    telegram_bot.save_settings(bot_token="x", channel_id="y", master_send_enabled=True)
    _open_position("champ")
    storage.upsert_paper_strategy_group("champ", "challenge", "2026-01-01T00:00:00+00:00")

    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        result = telegram_bot.send_signal_for_position(f"pos-champ", trigger_type="manual")

    assert result["ok"] is True
    sent_text = mock_send.call_args[0][0]
    assert sent_text.endswith(strategy_groups.CHALLENGE_TELEGRAM_MARKER)
    assert sent_text.endswith(",,,teen,,,")


@pytest.mark.parametrize("group_key", ["losing", "profitable"])
def test_non_challenge_group_signal_has_no_marker(test_db, group_key):
    telegram_bot.save_settings(bot_token="x", channel_id="y", master_send_enabled=True)
    _open_position("s1")
    storage.upsert_paper_strategy_group("s1", group_key, "2026-01-01T00:00:00+00:00")

    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        result = telegram_bot.send_signal_for_position("pos-s1", trigger_type="manual")

    assert result["ok"] is True
    sent_text = mock_send.call_args[0][0]
    assert strategy_groups.CHALLENGE_TELEGRAM_MARKER not in sent_text


def test_ungrouped_strategy_signal_has_no_marker(test_db):
    """A strategy that has never been assigned a group (get_group returns
    None) must never accidentally get the Challenge marker."""
    telegram_bot.save_settings(bot_token="x", channel_id="y", master_send_enabled=True)
    _open_position("unassigned")

    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        result = telegram_bot.send_signal_for_position("pos-unassigned", trigger_type="manual")

    assert result["ok"] is True
    sent_text = mock_send.call_args[0][0]
    assert strategy_groups.CHALLENGE_TELEGRAM_MARKER not in sent_text
