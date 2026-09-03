"""Grand Feature Expansion, Phase 3 Feature 11: Win-Rate Decay Detection
(paper_trading.insights.detect_win_rate_decay / sweep_win_rate_decay_alerts)
-- a standalone, always-on version of the same drift math
paper_trading.challenge_analysis.check_drift() already uses for active
Challenge Mode combos, but comparing against a strategy's OWN historical
baseline instead of a challenge-recorded one, so it works for every
strategy regardless of Challenge Mode.
"""

from datetime import datetime, timezone, timedelta

from data_engine import config as base_config, storage
from paper_trading import insights
from paper_trading.challenge_analysis import DRIFT_RECENT_TRADES_WINDOW, DRIFT_WIN_RATE_DROP_PTS

import pytest


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _close(position_id, pnl, strategy_id="strat1", days_ago=0):
    pos = {
        "id": position_id, "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": 1700000000000,
        "created_at": (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(),
        "strategy_id": strategy_id, "strategy_name": "Test Strategy",
    }
    storage.open_paper_position(pos)
    storage.close_paper_position(
        position_id, 100.0 + pnl, 1700000100000, pnl, pnl,
        "take_profit" if pnl >= 0 else "stop_loss", {}, {},
        (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(),
    )


def _seed(strategy_id, baseline_n, baseline_wins, recent_n, recent_wins):
    total = baseline_n + recent_n
    i = 0
    for _ in range(baseline_wins):
        _close(f"{strategy_id}_{i}", pnl=10.0, strategy_id=strategy_id, days_ago=total - i)
        i += 1
    for _ in range(baseline_n - baseline_wins):
        _close(f"{strategy_id}_{i}", pnl=-10.0, strategy_id=strategy_id, days_ago=total - i)
        i += 1
    for _ in range(recent_wins):
        _close(f"{strategy_id}_{i}", pnl=10.0, strategy_id=strategy_id, days_ago=total - i)
        i += 1
    for _ in range(recent_n - recent_wins):
        _close(f"{strategy_id}_{i}", pnl=-10.0, strategy_id=strategy_id, days_ago=total - i)
        i += 1


def test_not_enough_total_history_is_not_checked(test_db):
    _seed("strat1", baseline_n=5, baseline_wins=4, recent_n=5, recent_wins=1)
    result = insights.detect_win_rate_decay("strat1")
    assert result["checked"] is False
    assert result["drifted"] is None


def test_a_real_win_rate_drop_is_flagged(test_db):
    # Baseline: 25 trades, 80% win rate. Recent: 15 trades, 20% win rate --
    # a 60pt drop, far past the 15pt threshold.
    _seed("strat1", baseline_n=25, baseline_wins=20, recent_n=DRIFT_RECENT_TRADES_WINDOW, recent_wins=3)
    result = insights.detect_win_rate_decay("strat1")
    assert result["checked"] is True
    assert result["drifted"] is True
    assert result["baseline_win_rate_pct"] == 80.0
    assert result["win_rate_drop_pts"] >= DRIFT_WIN_RATE_DROP_PTS


def test_a_stable_win_rate_is_not_flagged(test_db):
    # Baseline and recent both ~53% -- no meaningful drift.
    _seed("strat1", baseline_n=25, baseline_wins=13, recent_n=DRIFT_RECENT_TRADES_WINDOW, recent_wins=8)
    result = insights.detect_win_rate_decay("strat1")
    assert result["checked"] is True
    assert result["drifted"] is False


def test_an_improving_win_rate_is_not_flagged(test_db):
    _seed("strat1", baseline_n=25, baseline_wins=5, recent_n=DRIFT_RECENT_TRADES_WINDOW, recent_wins=13)
    result = insights.detect_win_rate_decay("strat1")
    assert result["drifted"] is False


def test_sweep_creates_one_alert_per_decayed_strategy(test_db, monkeypatch):
    from backtest_engine import strategy_library as lib
    monkeypatch.setattr(lib, "list_all", lambda: [
        {"id": "strat1", "name": "Decayed Strategy"}, {"id": "strat2", "name": "Stable Strategy"},
    ])
    _seed("strat1", baseline_n=25, baseline_wins=20, recent_n=DRIFT_RECENT_TRADES_WINDOW, recent_wins=3)
    _seed("strat2", baseline_n=25, baseline_wins=13, recent_n=DRIFT_RECENT_TRADES_WINDOW, recent_wins=8)

    alerted = insights.sweep_win_rate_decay_alerts()
    assert alerted == ["strat1"]
    alerts = [a for a in storage.list_paper_alerts() if a["alert_type"] == "win_rate_decay"]
    assert len(alerts) == 1
    assert alerts[0]["strategy_id"] == "strat1"


def test_sweep_does_not_duplicate_within_the_recheck_window(test_db, monkeypatch):
    from backtest_engine import strategy_library as lib
    monkeypatch.setattr(lib, "list_all", lambda: [{"id": "strat1", "name": "Decayed Strategy"}])
    _seed("strat1", baseline_n=25, baseline_wins=20, recent_n=DRIFT_RECENT_TRADES_WINDOW, recent_wins=3)

    first = insights.sweep_win_rate_decay_alerts()
    second = insights.sweep_win_rate_decay_alerts()
    assert first == ["strat1"]
    assert second == []
    alerts = [a for a in storage.list_paper_alerts() if a["alert_type"] == "win_rate_decay"]
    assert len(alerts) == 1
