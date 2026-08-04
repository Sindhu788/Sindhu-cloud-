"""Batch 9, Task 4: Challenge Mode. Tracking/reporting only -- these
tests specifically confirm it NEVER touches risk_pct, position sizing,
or any other trading behavior, alongside the pace-calculation and
progress-tracking math itself.
"""

from datetime import datetime, timedelta, timezone

import pytest

from data_engine import config as base_config, storage
from paper_trading import challenge_mode, config as pt_config


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _iso(days_ago):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _open_position(**overrides):
    pos = {
        "id": "pos1", "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": 1700000000000, "created_at": _iso(10),
        "strategy_id": "strat1", "strategy_name": "Test Strategy",
    }
    pos.update(overrides)
    storage.open_paper_position(pos)
    return pos


def _close(position_id, pnl, closed_at):
    storage.close_paper_position(position_id, 100.0, 1700000100000, pnl, pnl, "take_profit", {}, {}, closed_at)


# ------------------------------------------------------------- set_challenge

def test_set_challenge_requires_all_three_numbers():
    with pytest.raises(ValueError):
        challenge_mode.set_challenge(None, 200.0, 30)
    with pytest.raises(ValueError):
        challenge_mode.set_challenge(100.0, None, 30)
    with pytest.raises(ValueError):
        challenge_mode.set_challenge(100.0, 200.0, None)


def test_set_challenge_rejects_non_positive_amount_or_days():
    with pytest.raises(ValueError):
        challenge_mode.set_challenge(0, 200.0, 30)
    with pytest.raises(ValueError):
        challenge_mode.set_challenge(100.0, 200.0, 0)


def test_set_challenge_persists_the_exact_user_chosen_numbers():
    challenge_mode.set_challenge(137.5, 999.0, 45)
    settings = challenge_mode.load()
    assert settings["start_amount"] == 137.5
    assert settings["target_amount"] == 999.0
    assert settings["days"] == 45
    assert settings["enabled"] is True


def test_compute_progress_is_none_when_no_challenge_configured():
    assert challenge_mode.compute_progress() is None


def test_clear_challenge_disables_it():
    challenge_mode.set_challenge(100.0, 200.0, 30)
    challenge_mode.clear_challenge()
    assert challenge_mode.compute_progress() is None


# ------------------------------------------------------------- required pace math

def test_required_daily_rate_matches_hand_computed_compound_formula():
    # Doubling in 10 days: (2)^(1/10) - 1
    rate = challenge_mode._required_daily_rate(100.0, 200.0, 10)
    assert rate == pytest.approx(2.0 ** (1 / 10) - 1, rel=1e-6)


def test_required_daily_rate_is_zero_when_target_already_met_or_below_start():
    assert challenge_mode._required_daily_rate(100.0, 100.0, 30) == 0.0
    assert challenge_mode._required_daily_rate(100.0, 50.0, 30) == 0.0


# ------------------------------------------------------------- honesty / realism

def test_flags_unrealistic_when_required_pace_dwarfs_real_history(test_db):
    # Real history: one modest winning trade 10 days ago -> a small real
    # daily rate. Target: 1000% in 5 days -- wildly beyond that.
    _open_position(id="p1")
    _close("p1", 1.0, _iso(9))  # R-multiple = 1.0/5.0 = 0.2

    challenge_mode.set_challenge(100.0, 1100.0, 5, now_iso=_iso(9))
    progress = challenge_mode.compute_progress()

    assert progress["realistic"] is False
    assert "REALISTIC NAHI" in progress["honest_note"]
    assert progress["closed_trades_used_for_baseline"] == 1


def test_realistic_flag_is_none_with_zero_real_trading_history(test_db):
    challenge_mode.set_challenge(100.0, 200.0, 30)
    progress = challenge_mode.compute_progress()
    assert progress["realistic"] is None
    assert "koi trade band nahi hua" in progress["honest_note"]


def test_marks_realistic_when_required_pace_is_within_real_demonstrated_range(test_db):
    # Real history: consistent small real winning trades over 30 days.
    for i in range(20):
        pid = f"p{i}"
        _open_position(id=pid, created_at=_iso(30))
        _close(pid, 1.0, _iso(29 - i))  # R-multiple = 0.2 each
    # A very modest target (1% total over 30 days) should be well within reach.
    challenge_mode.set_challenge(100.0, 101.0, 30, now_iso=_iso(29))
    progress = challenge_mode.compute_progress()
    assert progress["realistic"] is True
    assert "mumkin nazar aata hai" in progress["honest_note"]


# ------------------------------------------------------------- progress tracking

def test_current_amount_reflects_real_closed_trades_since_challenge_started(test_db):
    challenge_mode.set_challenge(100.0, 200.0, 30, now_iso=_iso(5))
    _open_position(id="p1", created_at=_iso(4))
    _close("p1", 10.0, _iso(3))  # R-multiple = 10/5 = 2.0 -> at 100 start, risk_per_trade=1.0 (1% default) -> +2.0
    progress = challenge_mode.compute_progress()
    # risk_pct_default is 1.0% by default -> risk_per_trade = 100 * 0.01 = 1.0; R=2.0 -> pnl contribution = 2.0
    assert progress["current_amount"] == pytest.approx(102.0, abs=0.01)
    assert progress["trades_counted"] == 1


def test_trades_closed_before_challenge_started_are_never_counted(test_db):
    _open_position(id="old", created_at=_iso(20))
    _close("old", 500.0, _iso(15))  # huge win, but BEFORE the challenge starts
    challenge_mode.set_challenge(100.0, 200.0, 30, now_iso=_iso(5))
    progress = challenge_mode.compute_progress()
    assert progress["current_amount"] == pytest.approx(100.0, abs=0.01)
    assert progress["trades_counted"] == 0


def test_progress_pct_and_time_fields_are_computed_honestly(test_db):
    challenge_mode.set_challenge(100.0, 200.0, 20, now_iso=_iso(10))
    progress = challenge_mode.compute_progress()
    assert progress["elapsed_days"] == pytest.approx(10.0, abs=0.05)
    assert progress["remaining_days"] == pytest.approx(10.0, abs=0.05)
    assert 0.0 <= progress["progress_pct"] <= 100.0


# ------------------------------------------------------------- never touches trading behavior

def test_challenge_mode_never_modifies_risk_pct_or_any_trading_setting(test_db):
    before = dict(pt_config.load())
    _open_position(id="p1")
    _close("p1", 5.0, _iso(1))
    challenge_mode.set_challenge(100.0, 500.0, 10, now_iso=_iso(2))
    challenge_mode.compute_progress()
    after = dict(pt_config.load())
    assert before == after
