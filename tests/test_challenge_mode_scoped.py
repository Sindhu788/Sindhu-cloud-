"""Level 3 of the Challenge Mode redesign: one-click start against a
specific real strategy-coin combination, live tracking against that
combo's own real pace (not the system-wide blend), and proactive drift
warnings. Also confirms starting a scoped challenge never touches any
trading/risk setting -- same absolute safety principle as the unscoped
mode.
"""

from datetime import datetime, timedelta, timezone

import pytest

from data_engine import config as base_config, storage
from paper_trading import challenge_mode, config as pt_config


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _iso(days_ago):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _trade(pid, strategy_id, symbol, pnl, risk_amount, closed_days_ago, entry_time_ms=1700000000000):
    storage.open_paper_position({
        "id": pid, "exchange": "binance", "symbol": symbol, "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": risk_amount,
        "entry_time": entry_time_ms, "created_at": _iso(closed_days_ago),
        "strategy_id": strategy_id, "strategy_name": strategy_id,
    })
    storage.close_paper_position(pid, 100.0, entry_time_ms + 60000, pnl, pnl, "take_profit", {}, {}, _iso(closed_days_ago))


def test_scoped_challenge_captures_baseline_win_rate_at_start(test_db):
    for i in range(10):
        pnl = 3.0 if i < 8 else -3.0  # 80% baseline win rate
        _trade(f"p{i}", "stratX", "BTCUSDT", pnl, 5.0, closed_days_ago=10 - i)

    settings = challenge_mode.set_challenge(100.0, 200.0, 30, scope_strategy_id="stratX", scope_symbol="BTCUSDT")
    assert settings["scope_strategy_id"] == "stratX"
    assert settings["scope_symbol"] == "BTCUSDT"
    assert settings["baseline_win_rate_pct"] == 80.0


def test_scoped_challenge_tracks_only_its_own_combos_trades_not_other_strategies(test_db):
    # Two strategies both trading; the challenge is scoped to stratX only.
    _trade("x1", "stratX", "BTCUSDT", 20.0, 5.0, closed_days_ago=3)
    challenge_mode.set_challenge(100.0, 200.0, 30, now_iso=_iso(5), scope_strategy_id="stratX", scope_symbol="BTCUSDT")
    _trade("y1", "stratY", "ETHUSDT", 1000.0, 5.0, closed_days_ago=1)  # huge win, but a DIFFERENT combo

    progress = challenge_mode.compute_progress()
    # Only stratX/BTCUSDT's trade counts -- stratY's huge win must be ignored.
    assert progress["trades_counted"] == 1
    risk_pct = pt_config.load().get("risk_pct_default", 1.0) / 100.0
    expected = 100.0 + (20.0 / 5.0) * (100.0 * risk_pct)
    assert progress["current_amount"] == pytest.approx(expected, abs=0.01)


def test_scoped_challenge_projected_finish_date_uses_realized_pace(test_db):
    challenge_mode.set_challenge(100.0, 200.0, 60, now_iso=_iso(10), scope_strategy_id="stratX", scope_symbol="BTCUSDT")
    for i in range(5):
        _trade(f"z{i}", "stratX", "BTCUSDT", 5.0, 5.0, closed_days_ago=9 - i)
    progress = challenge_mode.compute_progress()
    assert progress["current_amount"] > progress["start_amount"]
    assert progress["projected_finish_date"] is not None
    assert progress["realized_daily_rate_pct"] is not None
    assert progress["realized_daily_rate_pct"] > 0


def test_scoped_challenge_surfaces_drift_warning_when_combo_degrades(test_db):
    for i in range(10):
        _trade(f"base{i}", "stratX", "BTCUSDT", 3.0, 5.0, closed_days_ago=40 - i)
    settings = challenge_mode.set_challenge(100.0, 500.0, 90, now_iso=_iso(35),
                                             scope_strategy_id="stratX", scope_symbol="BTCUSDT")
    assert settings["baseline_win_rate_pct"] == 100.0

    # Now the combo degrades badly -- most of the recent trades lose.
    for i in range(15):
        pnl = -2.0 if i < 12 else 2.0  # 20% recent win rate vs 100% baseline
        _trade(f"recent{i}", "stratX", "BTCUSDT", pnl, 5.0, closed_days_ago=15 - i)

    progress = challenge_mode.compute_progress()
    assert progress["drift"] is not None
    assert progress["drift"]["checked"] is True
    assert progress["drift"]["drifted"] is True


def test_starting_a_scoped_challenge_never_touches_trading_settings(test_db):
    _trade("s1", "stratX", "BTCUSDT", 5.0, 5.0, closed_days_ago=1)
    before = dict(pt_config.load())
    challenge_mode.set_challenge(100.0, 500.0, 30, scope_strategy_id="stratX", scope_symbol="BTCUSDT")
    challenge_mode.compute_progress()
    after = dict(pt_config.load())
    assert before == after


def test_unscoped_challenge_behavior_is_completely_unchanged(test_db):
    """Backward-compat guard: a challenge started WITHOUT a scope must
    keep behaving exactly like the original single-aggregate mode."""
    settings = challenge_mode.set_challenge(100.0, 200.0, 30)
    assert settings["scope_strategy_id"] is None
    assert settings["scope_symbol"] is None
    assert settings["baseline_win_rate_pct"] is None
    progress = challenge_mode.compute_progress()
    assert progress["drift"] is None
