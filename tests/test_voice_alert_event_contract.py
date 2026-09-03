"""Grand Feature Expansion, Phase 4 Feature 26: Voice Alert on critical
events. The actual speech happens client-side (sindhu_web/static/js/app.js's
VOICE_ALERT_EVENTS, keyed by "entity:action") -- nothing to unit-test in
Python for the browser speechSynthesis call itself, but this locks in the
CONTRACT: the exact (entity, action) pairs the frontend listens for must
keep being emitted by kill_switch.activate() and
account_drawdown_guard.evaluate_account(), or a future refactor could
silently break the voice alert with no test ever catching it.
"""

from unittest.mock import patch

from data_engine import config as base_config, storage
from paper_trading import account_drawdown_guard, kill_switch

import pytest


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _close(position_id, pnl, strategy_id="strat1"):
    storage.open_paper_position({
        "id": position_id, "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": 1700000000000, "created_at": "2026-01-01T00:00:00+00:00",
        "strategy_id": strategy_id, "strategy_name": strategy_id,
    })
    storage.close_paper_position(position_id, 100.0 + pnl, 1700000100000, pnl, pnl,
                                  "take_profit" if pnl >= 0 else "stop_loss", {}, {}, "2026-01-02T00:00:00+00:00")


def test_kill_switch_activation_emits_the_exact_event_the_frontend_listens_for(test_db):
    # sync is imported lazily inside kill_switch.activate() (from sindhu_web
    # import sync), so the patch target is the real sindhu_web.sync module
    # itself, not paper_trading.kill_switch.sync (which never exists as a
    # module-level attribute there).
    with patch("sindhu_web.sync.notify") as mock_notify:
        kill_switch.activate(reason="test", close_positions=False)
    entity, action = mock_notify.call_args[0][0], mock_notify.call_args[0][1]
    assert (entity, action) == ("kill_switch", "activated")


def test_account_drawdown_pause_emits_the_exact_event_the_frontend_listens_for(test_db):
    _close("p1", pnl=10.0)
    account_drawdown_guard.evaluate_account()  # seed the peak
    _close("p2", pnl=-3000.0)
    with patch("sindhu_web.sync.notify") as mock_notify:
        reason = account_drawdown_guard.evaluate_account()
    assert reason is not None  # the pause genuinely triggered
    entity, action = mock_notify.call_args[0][0], mock_notify.call_args[0][1]
    assert (entity, action) == ("account_drawdown", "paused")
