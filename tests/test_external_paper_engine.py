"""External Signal Tracker, Phase 3 -- isolated paper trading engine.
Proves: DCA entries fill in stages as price genuinely reaches them
(never immediately), stop-loss/take-profit close positions correctly,
per-channel balance/PnL is tracked independently, and none of this ever
touches paper_positions/paper_account_state/paper_strategy_performance."""

import os
import tempfile

import pytest

import data_engine.storage as storage
from external_signals import paper_engine


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", os.path.join(tempfile.mkdtemp(), "test.db"))
    storage.init_db()
    storage.save_external_channel("chA", "TEST Channel A", "@test_a", "Source A", "2026-01-01T00:00:00")
    storage.save_external_channel("chB", "TEST Channel B", "@test_b", "Source B", "2026-01-01T00:00:00")


def _dca_signal(channel_id="chA", direction="long"):
    return {
        "id": "sig1", "channel_id": channel_id, "symbol": "BTCUSDT", "direction": direction,
        "entries": [{"price": 65000.0, "size_pct": 50.0}, {"price": 64000.0, "size_pct": 50.0}],
        "stop_loss": 63000.0, "take_profit": [67000.0], "is_signal": True,
    }


def test_opening_a_dca_signal_fills_only_the_first_entry():
    pos_id = paper_engine.open_position_from_signal(_dca_signal())
    pos = storage.get_external_position(pos_id)
    assert pos["status"] == "open"
    assert pos["entries"][0]["filled"] is True
    assert pos["entries"][1]["filled"] is False
    assert pos["avg_entry_price"] == 65000.0
    assert pos["filled_size_pct"] == 50.0


def test_dca_second_entry_fills_only_when_price_genuinely_reaches_it(monkeypatch):
    pos_id = paper_engine.open_position_from_signal(_dca_signal())

    # Price is still above the second entry (64000) -- must NOT fill yet.
    monkeypatch.setattr(paper_engine, "_fetch_live_price", lambda symbol, exchange=None: 64500.0)
    events = paper_engine.check_price_updates()
    pos = storage.get_external_position(pos_id)
    assert pos["entries"][1]["filled"] is False
    assert not any(e["action"] == "dca_entry_filled" for e in events if e["position_id"] == pos_id)

    # Price genuinely drops to the second entry level -- must fill now.
    monkeypatch.setattr(paper_engine, "_fetch_live_price", lambda symbol, exchange=None: 64000.0)
    events = paper_engine.check_price_updates()
    pos = storage.get_external_position(pos_id)
    assert pos["entries"][1]["filled"] is True
    assert pos["filled_size_pct"] == 100.0
    assert pos["avg_entry_price"] == pytest.approx(64500.0)  # (65000*50 + 64000*50)/100
    assert any(e["action"] == "dca_entry_filled" and e["position_id"] == pos_id for e in events)


def test_stop_loss_closes_the_position_with_correct_negative_pnl(monkeypatch):
    pos_id = paper_engine.open_position_from_signal(_dca_signal())
    monkeypatch.setattr(paper_engine, "_fetch_live_price", lambda symbol, exchange=None: 63000.0)  # hits SL
    events = paper_engine.check_price_updates()
    assert any(e["action"] == "closed_stop_loss" and e["position_id"] == pos_id for e in events)

    pos = storage.get_external_position(pos_id)
    assert pos["status"] == "closed"
    assert pos["exit_reason"] == "stop_loss"
    assert pos["pnl"] < 0


def test_take_profit_closes_the_position_with_correct_positive_pnl(monkeypatch):
    pos_id = paper_engine.open_position_from_signal(_dca_signal())
    monkeypatch.setattr(paper_engine, "_fetch_live_price", lambda symbol, exchange=None: 67000.0)  # hits TP
    events = paper_engine.check_price_updates()
    assert any(e["action"] == "closed_take_profit" and e["position_id"] == pos_id for e in events)

    pos = storage.get_external_position(pos_id)
    assert pos["status"] == "closed"
    assert pos["exit_reason"] == "take_profit"
    assert pos["pnl"] > 0


def test_short_signal_dca_direction_is_correct(monkeypatch):
    # A short's DCA entries realistically average UP as price rises
    # against the position: first entry 65000, second (worse) entry 66000.
    signal = {
        "id": "sig_short", "channel_id": "chA", "symbol": "BTCUSDT", "direction": "short",
        "entries": [{"price": 65000.0, "size_pct": 50.0}, {"price": 66000.0, "size_pct": 50.0}],
        "stop_loss": 67000.0, "take_profit": [63000.0], "is_signal": True,
    }
    pos_id = paper_engine.open_position_from_signal(signal)

    # Price hasn't risen to the second entry yet -- must NOT fill.
    monkeypatch.setattr(paper_engine, "_fetch_live_price", lambda symbol, exchange=None: 65500.0)
    paper_engine.check_price_updates()
    pos = storage.get_external_position(pos_id)
    assert pos["entries"][1]["filled"] is False

    # Price genuinely rises to the second entry level -- must fill now.
    monkeypatch.setattr(paper_engine, "_fetch_live_price", lambda symbol, exchange=None: 66000.0)
    paper_engine.check_price_updates()
    pos = storage.get_external_position(pos_id)
    assert pos["entries"][1]["filled"] is True


def test_missing_stop_loss_gets_the_same_emergency_fallback_as_paper_trading(monkeypatch):
    """Reuses backtest_engine.engine.EMERGENCY_STOP_PCT -- never leaves a
    position genuinely unprotected, matching the already-fixed paper
    trading behavior exactly."""
    from backtest_engine.engine import EMERGENCY_STOP_PCT
    signal = _dca_signal()
    signal["stop_loss"] = None
    pos_id = paper_engine.open_position_from_signal(signal)
    pos = storage.get_external_position(pos_id)
    expected = 65000.0 * (1 - EMERGENCY_STOP_PCT)
    assert pos["stop_loss"] == pytest.approx(expected)


def test_wrong_side_stop_loss_is_discarded_and_replaced_with_emergency_stop():
    signal = _dca_signal()
    signal["stop_loss"] = 66000.0  # ABOVE entry on a LONG -- nonsensical, must be discarded
    pos_id = paper_engine.open_position_from_signal(signal)
    pos = storage.get_external_position(pos_id)
    assert pos["stop_loss"] < 65000.0  # replaced by the emergency fallback, not trusted as-is


def test_channels_are_tracked_completely_independently(monkeypatch):
    pos_a = paper_engine.open_position_from_signal(_dca_signal(channel_id="chA"))
    pos_b = paper_engine.open_position_from_signal({**_dca_signal(channel_id="chB"), "id": "sig2"})

    monkeypatch.setattr(paper_engine, "_fetch_live_price", lambda symbol, exchange=None: 67000.0)
    paper_engine.check_price_updates()  # closes BOTH at take-profit

    perf_a = storage.get_external_channel_performance("chA")
    perf_b = storage.get_external_channel_performance("chB")
    assert perf_a["trades"] == 1
    assert perf_b["trades"] == 1
    assert perf_a["total_pnl"] == pytest.approx(perf_b["total_pnl"])  # identical signals -> identical result, independently computed
    assert perf_a["balance"] != 1000.0  # each channel's OWN balance moved


def test_manual_close_and_move_stop_loss_updates():
    pos_id = paper_engine.open_position_from_signal(_dca_signal())
    assert paper_engine.move_stop_loss(pos_id, 64800.0) is True
    pos = storage.get_external_position(pos_id)
    assert pos["stop_loss"] == 64800.0

    assert paper_engine.close_position_manually(pos_id, 65500.0, "manual_close") is True
    pos = storage.get_external_position(pos_id)
    assert pos["status"] == "closed"
    assert pos["exit_reason"] == "manual_close"


def test_never_writes_to_the_users_own_paper_trading_tables():
    """Direct isolation proof: opening/closing/DCA-filling external
    positions must never create rows in paper_positions or
    paper_account_state."""
    with storage.get_conn() as conn:
        before_positions = conn.execute("SELECT COUNT(*) FROM paper_positions").fetchone()[0]
        before_account = conn.execute("SELECT COUNT(*) FROM paper_account_state").fetchone()[0]

    pos_id = paper_engine.open_position_from_signal(_dca_signal())
    paper_engine.close_position_manually(pos_id, 65500.0, "manual_close")

    with storage.get_conn() as conn:
        after_positions = conn.execute("SELECT COUNT(*) FROM paper_positions").fetchone()[0]
        after_account = conn.execute("SELECT COUNT(*) FROM paper_account_state").fetchone()[0]
    assert after_positions == before_positions
    assert after_account == before_account
