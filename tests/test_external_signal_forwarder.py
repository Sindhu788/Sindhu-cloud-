"""External Signal Tracker -- Phase 5: proving threshold, eligibility
(30 trades AND profitable -- the CEO's own explicit decision), privacy
(source name never leaked), and the Signal Freshness Gate reuse."""

import os
import tempfile
import time

import pytest

import data_engine.storage as storage
from external_signals import channels, forwarder, paper_engine, config as ext_config
from paper_trading import telegram_bot as pt_telegram_bot


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", os.path.join(tempfile.mkdtemp(), "test.db"))
    storage.init_db()
    monkeypatch.setattr(ext_config, "load", lambda: {
        **ext_config._DEFAULTS,
        "forward_bot_token": "TEST_TOKEN", "forward_channel_id": "TEST_CHAT_ID",
        "forwarding_enabled": True, "proving_trades_required": 30,
        "require_profitable_to_forward": True,
    })
    # freshness_check() internally fetches a REAL live price via the
    # exchange client -- never let a test hit the real network.
    monkeypatch.setattr(pt_telegram_bot, "_fetch_live_price", lambda exchange, symbol: 65000.0)


def _closed_trades(channel_id, n, entry=65000.0, winning=True):
    exit_price = entry * 1.05 if winning else entry * 0.95
    for i in range(n):
        signal = {"id": f"s{i}", "channel_id": channel_id, "symbol": "BTCUSDT", "direction": "long",
                  "entries": [{"price": entry, "size_pct": 100.0}], "stop_loss": entry * 0.97,
                  "take_profit": [], "is_signal": True}
        pos_id = paper_engine.open_position_from_signal(signal)
        paper_engine.close_position_manually(pos_id, exit_price, "manual_close")


def test_channel_under_30_trades_is_never_eligible():
    cid = channels.add_channel("TEST Channel", "@test")
    _closed_trades(cid, 29, winning=True)
    eligible, reason = forwarder.is_channel_eligible_for_forwarding(cid)
    assert eligible is False
    assert "29/30" in reason


def test_channel_at_30_trades_but_unprofitable_is_not_eligible():
    """The CEO's explicit decision: trade count alone is NOT enough."""
    cid = channels.add_channel("TEST Channel", "@test")
    _closed_trades(cid, 30, winning=False)
    eligible, reason = forwarder.is_channel_eligible_for_forwarding(cid)
    assert eligible is False
    assert "not profitable" in reason.lower()


def test_channel_at_30_trades_and_profitable_is_eligible():
    cid = channels.add_channel("TEST Channel", "@test")
    _closed_trades(cid, 30, winning=True)
    eligible, reason = forwarder.is_channel_eligible_for_forwarding(cid)
    assert eligible is True


def test_forwarded_message_never_contains_the_real_channel_name_or_handle():
    cid = channels.add_channel("Super Secret VIP Signals Group", "@secretsignalsvip123")
    channel = storage.get_external_channel(cid)
    signal = {"symbol": "BTCUSDT", "direction": "long",
              "entries": [{"price": 65000.0, "size_pct": 100.0}],
              "stop_loss": 63000.0, "take_profit": [67000.0], "leverage": 10}
    text = forwarder.format_forwarded_message(channel, signal)
    assert "Super Secret VIP Signals Group" not in text
    assert "@secretsignalsvip123" not in text
    assert "secretsignalsvip" not in text.lower()
    assert channel["forwarding_source_label"] in text  # the stable generic label IS present


def test_forwarded_message_is_emoji_led_and_scannable():
    channel = {"forwarding_source_label": "Source A"}
    signal = {"symbol": "BTCUSDT", "direction": "long",
              "entries": [{"price": 65000.0, "size_pct": 50.0}, {"price": 64000.0, "size_pct": 50.0}],
              "stop_loss": 63000.0, "take_profit": [67000.0, 69000.0], "leverage": None}
    text = forwarder.format_forwarded_message(channel, signal)
    lines = [l for l in text.split("\n") if l.strip()]
    assert len(lines) >= 5
    assert any(ord(c) > 0x2600 for c in lines[0])  # emoji in the first line
    assert all(len(l) < 220 for l in lines)
    for forbidden in ("strategy_id", "confluence_score", "candle_break", "pnl_pct"):
        assert forbidden not in text


def test_forwarded_message_shows_multiple_dca_entries():
    channel = {"forwarding_source_label": "Source A"}
    signal = {"symbol": "BTCUSDT", "direction": "long",
              "entries": [{"price": 65000.0, "size_pct": 50.0}, {"price": 64000.0, "size_pct": 50.0}],
              "stop_loss": 63000.0, "take_profit": [67000.0], "leverage": None}
    text = forwarder.format_forwarded_message(channel, signal)
    assert "65000" in text and "64000" in text
    assert "Entries" in text  # plural, since this is a DCA signal


def test_stale_signal_is_withheld_not_forwarded(monkeypatch):
    """Reuses the real Signal Freshness Gate -- a signal received 30
    minutes ago (default limit 15) must be withheld, never sent late."""
    cid = channels.add_channel("TEST Channel", "@test")
    _closed_trades(cid, 30, winning=True)

    monkeypatch.setattr(forwarder, "_raw_send", lambda *a, **k: (True, None))
    old_entry_time_ms = int(time.time() * 1000) - (30 * 60 * 1000)  # 30 minutes ago
    signal = {"symbol": "BTCUSDT", "direction": "long",
              "entries": [{"price": 65000.0, "size_pct": 100.0}],
              "stop_loss": 63000.0, "take_profit": [67000.0], "leverage": None}
    result = forwarder.forward_signal_if_eligible(cid, signal, old_entry_time_ms)
    assert result["forwarded"] is False
    assert "stale" in result["reason"].lower() or "old" in result["reason"].lower() or "withheld" in result["reason"].lower()


def test_fresh_signal_from_an_eligible_channel_is_forwarded(monkeypatch):
    cid = channels.add_channel("TEST Channel", "@test")
    _closed_trades(cid, 30, winning=True)

    sent = {}
    def fake_send(text, bot_token, channel_id, timeout=15):
        sent["text"], sent["bot_token"], sent["channel_id"] = text, bot_token, channel_id
        return True, None
    monkeypatch.setattr(forwarder, "_raw_send", fake_send)

    fresh_entry_time_ms = int(time.time() * 1000)
    signal = {"symbol": "BTCUSDT", "direction": "long",
              "entries": [{"price": 65000.0, "size_pct": 100.0}],
              "stop_loss": 63000.0, "take_profit": [67000.0], "leverage": None}
    result = forwarder.forward_signal_if_eligible(cid, signal, fresh_entry_time_ms)
    assert result["forwarded"] is True
    assert sent["bot_token"] == "TEST_TOKEN"
    assert sent["channel_id"] == "TEST_CHAT_ID"
    assert "BTCUSDT" in sent["text"]


def test_unproven_channels_signals_are_never_forwarded_only_tracked_silently(monkeypatch):
    cid = channels.add_channel("TEST Channel", "@test")
    _closed_trades(cid, 5, winning=True)  # nowhere near 30

    called = {"n": 0}
    monkeypatch.setattr(forwarder, "_raw_send", lambda *a, **k: called.__setitem__("n", called["n"] + 1) or (True, None))
    signal = {"symbol": "BTCUSDT", "direction": "long",
              "entries": [{"price": 65000.0, "size_pct": 100.0}],
              "stop_loss": 63000.0, "take_profit": [67000.0], "leverage": None}
    result = forwarder.forward_signal_if_eligible(cid, signal, int(time.time() * 1000))
    assert result["forwarded"] is False
    assert called["n"] == 0  # send was never even attempted
