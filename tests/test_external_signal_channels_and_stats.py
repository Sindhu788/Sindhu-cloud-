"""External Signal Tracker -- Phase 1 (channel management) and Phase 4
(per-channel results dashboard + honest cross-channel comparison)."""

import os
import tempfile

import pytest

import data_engine.storage as storage
from external_signals import channels, channel_stats, paper_engine


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", os.path.join(tempfile.mkdtemp(), "test.db"))
    storage.init_db()


def test_multiple_channels_supported_from_the_start():
    id_a = channels.add_channel("TEST Channel A", "@test_a")
    id_b = channels.add_channel("TEST Channel B", "@test_b")
    all_channels = channels.list_channels()
    assert len(all_channels) == 2
    assert {c["id"] for c in all_channels} == {id_a, id_b}


def test_each_channel_gets_a_distinct_stable_source_label():
    id_a = channels.add_channel("TEST Channel A", "@test_a")
    id_b = channels.add_channel("TEST Channel B", "@test_b")
    labels = {c["id"]: c["forwarding_source_label"] for c in channels.list_channels()}
    assert labels[id_a] != labels[id_b]
    assert labels[id_a] == "Source A"
    assert labels[id_b] == "Source B"


def test_enable_disable_and_rename():
    cid = channels.add_channel("TEST Channel", "@test")
    channels.set_enabled(cid, False)
    assert storage.get_external_channel(cid)["enabled"] == 0
    channels.set_enabled(cid, True)
    assert storage.get_external_channel(cid)["enabled"] == 1
    channels.rename(cid, "Renamed Channel")
    assert storage.get_external_channel(cid)["name"] == "Renamed Channel"


def test_removing_a_channel_never_deletes_its_trade_history():
    cid = channels.add_channel("TEST Channel", "@test")
    signal = {"id": "s1", "channel_id": cid, "symbol": "BTCUSDT", "direction": "long",
              "entries": [{"price": 65000.0, "size_pct": 100.0}], "stop_loss": 63000.0,
              "take_profit": [67000.0], "is_signal": True}
    pos_id = paper_engine.open_position_from_signal(signal)
    paper_engine.close_position_manually(pos_id, 66000.0, "manual_close")

    channels.remove(cid)
    assert storage.get_external_channel(cid) is None
    # The closed position itself is never deleted.
    assert storage.get_external_position(pos_id) is not None


def _closed_trade(channel_id, entry, exit_price, direction="long", sl=None, tp=None):
    signal = {"id": f"s-{entry}-{exit_price}", "channel_id": channel_id, "symbol": "BTCUSDT", "direction": direction,
              "entries": [{"price": entry, "size_pct": 100.0}], "stop_loss": sl or (entry * 0.97 if direction == "long" else entry * 1.03),
              "take_profit": [tp] if tp else [], "is_signal": True}
    pos_id = paper_engine.open_position_from_signal(signal)
    paper_engine.close_position_manually(pos_id, exit_price, "manual_close")


def test_channel_report_reflects_real_stored_records_only():
    cid = channels.add_channel("TEST Channel", "@test")
    _closed_trade(cid, 65000, 66000)  # winner
    _closed_trade(cid, 65000, 64000)  # loser

    report = channel_stats.channel_report(cid)
    assert report["closed_trades"] == 2
    assert report["win_rate_pct"] == 50.0
    assert report["is_proven_sample_size"] is False  # only 2/30


def test_open_trades_are_never_mixed_into_closed_counts():
    cid = channels.add_channel("TEST Channel", "@test")
    _closed_trade(cid, 65000, 66000)
    signal = {"id": "s-open", "channel_id": cid, "symbol": "ETHUSDT", "direction": "long",
              "entries": [{"price": 3000.0, "size_pct": 100.0}], "stop_loss": 2900.0,
              "take_profit": [3200.0], "is_signal": True}
    paper_engine.open_position_from_signal(signal)  # left open

    report = channel_stats.channel_report(cid)
    assert report["closed_trades"] == 1
    assert report["open_trades"] == 1


def test_low_sample_channel_is_honestly_labeled_unproven():
    cid = channels.add_channel("TEST Channel", "@test")
    _closed_trade(cid, 65000, 66000)
    comparison = channel_stats.comparison_view()
    row = next(r for r in comparison if r["channel_id"] == cid)
    assert "Unproven" in row["honest_label"]
    assert "1/30" in row["honest_label"]


def test_channels_are_never_averaged_together_in_comparison_view():
    id_a = channels.add_channel("TEST Channel A", "@test_a")
    id_b = channels.add_channel("TEST Channel B", "@test_b")
    _closed_trade(id_a, 65000, 70000)   # big winner
    _closed_trade(id_b, 65000, 64000)   # loser

    comparison = channel_stats.comparison_view()
    row_a = next(r for r in comparison if r["channel_id"] == id_a)
    row_b = next(r for r in comparison if r["channel_id"] == id_b)
    assert row_a["total_pnl"] != row_b["total_pnl"]
    assert row_a["total_pnl"] > 0
    assert row_b["total_pnl"] < 0


def test_best_and_worst_coin_are_computed_from_real_records():
    cid = channels.add_channel("TEST Channel", "@test")
    _closed_trade(cid, 65000, 70000)  # BTCUSDT winner
    signal = {"id": "s-eth", "channel_id": cid, "symbol": "ETHUSDT", "direction": "long",
              "entries": [{"price": 3000.0, "size_pct": 100.0}], "stop_loss": 2900.0,
              "take_profit": [], "is_signal": True}
    pos_id = paper_engine.open_position_from_signal(signal)
    paper_engine.close_position_manually(pos_id, 2800.0, "manual_close")  # loser

    report = channel_stats.channel_report(cid)
    assert report["best_coin"]["symbol"] == "BTCUSDT"
    assert report["worst_coin"]["symbol"] == "ETHUSDT"
