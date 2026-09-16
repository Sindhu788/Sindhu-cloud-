"""2026-09-16 audit, CEO Section 10.1: per-strategy cooling-off period after
consecutive losses (paper_trading/cooling_off.py). Only ever blocks NEW
entries for one strategy, expires on its own, and never affects another
strategy or any existing gate."""

from datetime import datetime, timedelta, timezone

import pytest

from data_engine import config as base_config, storage
from paper_trading import cooling_off


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


SETTINGS = {"cooling_off_loss_streak": 3, "cooling_off_hours": 2.0}


def _closed(strategy_id, pnl, closed_at, pos_id):
    ms = int(closed_at.timestamp() * 1000)
    storage.open_paper_position({
        "id": pos_id, "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0, "entry_time": ms,
        "created_at": closed_at.isoformat(), "strategy_id": strategy_id, "strategy_name": strategy_id,
    })
    storage.close_paper_position(
        pos_id, exit_price=100.0 + pnl, exit_time=ms, pnl=pnl, pnl_pct=pnl,
        exit_reason="stop_loss" if pnl < 0 else "take_profit", lifecycle={}, reflection={},
        closed_at=closed_at.isoformat(), book_key=strategy_id,
    )


def test_active_after_streak_of_losses_within_window(test_db):
    now = datetime.now(timezone.utc)
    for i in range(3):
        _closed("s1", -1.0, now - timedelta(minutes=30 - i), f"p{i}")
    active, reason, until = cooling_off.check("s1", SETTINGS, now=now)
    assert active is True
    assert "3 consecutive losses" in reason
    assert datetime.fromisoformat(until) > now


def test_expires_on_its_own_after_the_window(test_db):
    now = datetime.now(timezone.utc)
    for i in range(3):
        _closed("s1", -1.0, now - timedelta(hours=3, minutes=i), f"p{i}")
    assert cooling_off.check("s1", SETTINGS, now=now)[0] is False


def test_a_win_in_the_latest_trades_breaks_the_streak(test_db):
    now = datetime.now(timezone.utc)
    _closed("s1", -1.0, now - timedelta(minutes=40), "p0")
    _closed("s1", -1.0, now - timedelta(minutes=30), "p1")
    _closed("s1", 2.0, now - timedelta(minutes=20), "p2")
    _closed("s1", -1.0, now - timedelta(minutes=10), "p3")
    assert cooling_off.check("s1", SETTINGS, now=now)[0] is False


def test_uses_the_latest_trades_not_the_oldest(test_db):
    now = datetime.now(timezone.utc)
    for i in range(3):  # old losing streak, long ago
        _closed("s1", -1.0, now - timedelta(days=2, minutes=i), f"old{i}")
    _closed("s1", 5.0, now - timedelta(minutes=30), "win")
    for i in range(3):  # fresh losing streak
        _closed("s1", -1.0, now - timedelta(minutes=20 - i), f"new{i}")
    assert cooling_off.check("s1", SETTINGS, now=now)[0] is True


def test_scoped_to_one_strategy_only(test_db):
    now = datetime.now(timezone.utc)
    for i in range(3):
        _closed("s1", -1.0, now - timedelta(minutes=30 - i), f"p{i}")
    _closed("s2", -1.0, now - timedelta(minutes=5), "q0")
    assert cooling_off.check("s1", SETTINGS, now=now)[0] is True
    assert cooling_off.check("s2", SETTINGS, now=now)[0] is False


def test_zero_streak_turns_it_off(test_db):
    now = datetime.now(timezone.utc)
    for i in range(5):
        _closed("s1", -1.0, now - timedelta(minutes=30 - i), f"p{i}")
    assert cooling_off.check("s1", {"cooling_off_loss_streak": 0, "cooling_off_hours": 2.0}, now=now)[0] is False


def test_not_enough_trades_is_never_a_cooling_off(test_db):
    now = datetime.now(timezone.utc)
    _closed("s1", -1.0, now - timedelta(minutes=5), "p0")
    assert cooling_off.check("s1", SETTINGS, now=now)[0] is False


def test_engine_rejects_entry_during_cooling_off(test_db, monkeypatch):
    """The engine's pre-entry path logs a 'rejected' decision with the
    cooling-off reason instead of opening -- checked via the real
    _open_if_allowed with every OTHER guard stubbed to allow."""
    from paper_trading import engine as engine_mod

    now = datetime.now(timezone.utc)
    for i in range(3):
        _closed("s1", -1.0, now - timedelta(minutes=30 - i), f"p{i}")

    eng = engine_mod.PaperTradingEngine.__new__(engine_mod.PaperTradingEngine)
    logged = []

    class _Guards:
        def reserve(self, *a):
            return True

    eng._guards = _Guards()
    eng._log_decision = lambda exchange, symbol, pick, decision, reason, snapshot, position_id=None: logged.append((decision, reason))
    opened, rejected = eng._open_if_allowed("s1", "binance", "BTCUSDT", {"direction": "bullish"}, {}, SETTINGS)
    assert (opened, rejected) == (0, 1)
    assert logged and logged[0][0] == "rejected" and logged[0][1].startswith("cooling-off:")
