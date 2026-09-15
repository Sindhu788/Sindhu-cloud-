"""Grand Master Batch #2, Phase 2.5: real evidence for the Signal
Congestion Filter -- when a DIFFERENT strategy already signaled the SAME
coin in the SAME direction recently, withhold the redundant confirmation.
Never touches the OPPOSITE-direction case (a genuinely different,
informational "conflicting setup" this deliberately does not auto-resolve).
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


def _open_and_log(pos_id, strategy_id, strategy_name, symbol, direction):
    storage.open_paper_position({
        "id": pos_id, "exchange": "binance", "symbol": symbol, "direction": direction,
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": int(datetime.now(timezone.utc).timestamp() * 1000),
        "created_at": "2026-01-01T00:00:00+00:00",
        "strategy_id": strategy_id, "strategy_name": strategy_name,
        "stop_loss": 90.0, "take_profit": 130.0,
    })
    storage.log_telegram_message(pos_id, strategy_id, strategy_name, "manual", "text", True, None,
                                  datetime.now(timezone.utc).isoformat())


def test_passes_open_with_no_other_recent_signal(test_db):
    _open_and_log("pos1", "stratA", "Strategy A", "BTCUSDT", "long")
    # No OTHER strategy has signaled BTCUSDT long yet.
    ok, reason = telegram_bot.congestion_check({"strategy_id": "stratA", "symbol": "BTCUSDT", "direction": "long"})
    assert ok is True and reason is None


def test_blocks_same_coin_same_direction_from_a_different_strategy(test_db):
    _open_and_log("pos1", "stratA", "Strategy A", "BTCUSDT", "long")
    ok, reason = telegram_bot.congestion_check({"strategy_id": "stratB", "symbol": "BTCUSDT", "direction": "long"})
    assert ok is False
    assert "Strategy A" in reason
    assert "redundant confirmation" in reason


def test_never_blocks_the_opposite_direction_conflicting_setup_case(test_db):
    _open_and_log("pos1", "stratA", "Strategy A", "BTCUSDT", "long")
    ok, reason = telegram_bot.congestion_check({"strategy_id": "stratB", "symbol": "BTCUSDT", "direction": "short"})
    assert ok is True and reason is None


def test_never_blocks_the_same_strategy_signaling_again(test_db):
    # duplicate_signal_check (Phase 2.6) already owns the same-strategy
    # case -- congestion_check must not double-block it.
    _open_and_log("pos1", "stratA", "Strategy A", "BTCUSDT", "long")
    ok, reason = telegram_bot.congestion_check({"strategy_id": "stratA", "symbol": "BTCUSDT", "direction": "long"})
    assert ok is True and reason is None


def test_wired_into_send_signal_for_position_blocks_a_real_send(test_db, monkeypatch):
    _open_and_log("pos1", "stratA", "Strategy A", "BTCUSDT", "long")
    storage.open_paper_position({
        "id": "pos2", "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": int(datetime.now(timezone.utc).timestamp() * 1000),
        "created_at": "2026-01-01T00:00:00+00:00",
        "strategy_id": "stratB", "strategy_name": "Strategy B",
        "stop_loss": 90.0, "take_profit": 130.0,
    })
    telegram_bot.save_settings(bot_token="x", channel_id="y", master_send_enabled=True)
    monkeypatch.setattr(telegram_bot, "_fetch_live_price", lambda *a, **k: None)
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        result = telegram_bot.send_signal_for_position("pos2", trigger_type="manual")
    mock_send.assert_not_called()
    assert result["ok"] is False
    assert "redundant confirmation" in result["error"]
