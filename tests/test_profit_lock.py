"""Grand Feature Expansion, Phase 5 Feature 9: Profit-Lock Trailing Stop
(paper_trading/profit_lock.py) -- once a position has moved favorably by
at least `trigger_r` times its own original risk, the stop-loss trails
behind the best price seen so far to lock in `trail_pct` of that move.
Confirmed absent at both the per-position and portfolio level before this
was built; the stop-loss is only ever tightened, never loosened.
"""

from datetime import datetime, timezone

import pytest

from data_engine import config as base_config
from paper_trading import position_manager, profit_lock


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def test_no_trigger_yet_returns_none_long():
    # Entry 100, stop 95 (risk=5). Price only reached 102 -- 0.4R, below
    # the default 1.0R trigger.
    new_stop = profit_lock.compute_trailing_stop("long", 100.0, 95.0, 102.0, 100.0, trigger_r=1.0, trail_pct=50.0)
    assert new_stop is None


def test_triggered_long_locks_in_the_configured_percentage():
    # Entry 100, stop 95 (risk=5). Price reached 110 -- 2R favorable move.
    # 50% lock-in -> new stop = 100 + (10 * 0.5) = 105.
    new_stop = profit_lock.compute_trailing_stop("long", 100.0, 95.0, 110.0, 100.0, trigger_r=1.0, trail_pct=50.0)
    assert new_stop == pytest.approx(105.0)


def test_triggered_short_locks_in_the_configured_percentage():
    # Entry 100, stop 105 (risk=5, short). Price reached 90 -- 2R favorable move.
    # 50% lock-in -> new stop = 100 - (10 * 0.5) = 95.
    new_stop = profit_lock.compute_trailing_stop("short", 100.0, 105.0, 100.0, 90.0, trigger_r=1.0, trail_pct=50.0)
    assert new_stop == pytest.approx(95.0)


def test_never_loosens_an_already_tighter_stop():
    # A manually-set stop of 106 is already tighter than what the trail
    # would compute (105) -- must not loosen it back out.
    new_stop = profit_lock.compute_trailing_stop("long", 100.0, 106.0, 110.0, 100.0, trigger_r=1.0, trail_pct=50.0)
    assert new_stop is None


def test_missing_stop_loss_returns_none():
    assert profit_lock.compute_trailing_stop("long", 100.0, None, 110.0, 100.0) is None


def test_zero_risk_returns_none():
    assert profit_lock.compute_trailing_stop("long", 100.0, 100.0, 110.0, 100.0) is None


def _open(position_id, direction, entry_price, stop_loss):
    from data_engine import storage
    storage.open_paper_position({
        "id": position_id, "exchange": "binance", "symbol": "BTCUSDT", "direction": direction,
        "entry_price": entry_price, "stop_loss": stop_loss, "size": 1.0, "risk_amount": 5.0,
        "entry_time": 1700000000000, "created_at": datetime.now(timezone.utc).isoformat(),
    })


def test_monitor_and_close_tightens_the_stop_when_enabled(test_db, monkeypatch):
    from paper_trading import config as pt_config

    settings = dict(pt_config._DEFAULTS)
    settings["profit_lock_enabled"] = True
    settings["profit_lock_trigger_r"] = 1.0
    settings["profit_lock_trail_pct"] = 50.0
    monkeypatch.setattr(pt_config, "load", lambda: settings)

    _open("pos1", "long", 100.0, 95.0)
    # Price runs up to 110 (2R) but stays well above both the original
    # stop (95) and the trade's take-profit-less range -- should not close,
    # only tighten the stop.
    closed = position_manager.monitor_and_close("binance", "BTCUSDT", 110.0, high=110.0, low=109.0)
    assert closed == []

    from data_engine import storage
    pos = storage.get_paper_position("pos1")
    assert pos["stop_loss"] == pytest.approx(105.0)


def test_monitor_and_close_leaves_stop_alone_when_disabled(test_db, monkeypatch):
    from paper_trading import config as pt_config

    settings = dict(pt_config._DEFAULTS)
    settings["profit_lock_enabled"] = False
    monkeypatch.setattr(pt_config, "load", lambda: settings)

    _open("pos2", "long", 100.0, 95.0)
    position_manager.monitor_and_close("binance", "BTCUSDT", 110.0, high=110.0, low=109.0)

    from data_engine import storage
    pos = storage.get_paper_position("pos2")
    assert pos["stop_loss"] == 95.0
