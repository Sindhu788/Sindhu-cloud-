"""Master Task 6, 2.5 -- Trailing Stop-Loss expanded from a single global
on/off switch to an optional per-strategy override. None (no override)
must fall back to the existing global paper_trading.config default exactly
as before; an explicit per-strategy True/False always wins."""

from datetime import datetime, timezone

from data_engine import config as base_config, storage
from paper_trading import config as pt_config, position_manager


def _open_position(strategy_id, entry=100.0, stop=95.0, direction="long"):
    pos = {
        "id": f"pos_{strategy_id}", "strategy_id": strategy_id, "strategy_name": strategy_id,
        "symbol": "BTCUSDT", "direction": direction, "entry_price": entry,
        "stop_loss": stop, "take_profit": entry + 20, "market_state": "trending_up",
        "session": "london", "entry_reason": "test", "exchange": "binance",
        "size": 1.0, "risk_amount": 5.0,
        "entry_time": int(datetime.now(timezone.utc).timestamp() * 1000),
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    storage.open_paper_position(pos)
    return pos


def test_global_default_off_means_no_trailing_without_any_override(test_db, tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    pt_config.update(profit_lock_enabled=False)
    _open_position("strat_a")
    # Price moves favorably well past a 1R trigger -- with the global
    # default OFF and no per-strategy override, the stop must stay untouched.
    position_manager.monitor_and_close("binance", "BTCUSDT", 120.0, high=120.0, low=119.0)
    pos = storage.get_paper_position("pos_strat_a")
    assert pos["stop_loss"] == 95.0


def test_per_strategy_override_true_enables_trailing_even_though_global_is_off(test_db, tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    pt_config.update(profit_lock_enabled=False, profit_lock_trigger_r=1.0, profit_lock_trail_pct=50.0)
    storage.set_strategy_signal_filter_overrides("strat_a", None, None, True, "2026-01-01T00:00:00+00:00")
    _open_position("strat_a")
    position_manager.monitor_and_close("binance", "BTCUSDT", 120.0, high=120.0, low=119.0)
    pos = storage.get_paper_position("pos_strat_a")
    assert pos["stop_loss"] > 95.0, "per-strategy override True must enable trailing even though the global default is off"


def test_per_strategy_override_false_disables_trailing_even_though_global_is_on(test_db, tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    pt_config.update(profit_lock_enabled=True, profit_lock_trigger_r=1.0, profit_lock_trail_pct=50.0)
    storage.set_strategy_signal_filter_overrides("strat_a", None, None, False, "2026-01-01T00:00:00+00:00")
    _open_position("strat_a")
    position_manager.monitor_and_close("binance", "BTCUSDT", 120.0, high=120.0, low=119.0)
    pos = storage.get_paper_position("pos_strat_a")
    assert pos["stop_loss"] == 95.0, "per-strategy override False must disable trailing even though the global default is on"


def test_a_different_strategys_position_is_unaffected_by_strat_as_override(test_db, tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    pt_config.update(profit_lock_enabled=False, profit_lock_trigger_r=1.0, profit_lock_trail_pct=50.0)
    storage.set_strategy_signal_filter_overrides("strat_a", None, None, True, "2026-01-01T00:00:00+00:00")
    _open_position("strat_b")
    position_manager.monitor_and_close("binance", "BTCUSDT", 120.0, high=120.0, low=119.0)
    pos = storage.get_paper_position("pos_strat_b")
    assert pos["stop_loss"] == 95.0
