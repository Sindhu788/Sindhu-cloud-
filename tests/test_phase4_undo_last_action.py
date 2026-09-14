"""Grand Master Batch, Phase 4 Item 11 -- Undo Last Action."""

import pytest

from data_engine import config as base_config, feature_toggles, storage
from paper_trading import drawdown_guard, kill_switch, undo_stack
from sindhu_web.api.activity import get_last_undoable_action, undo_last_action as undo_last_action_endpoint
from sindhu_web.api.feature_control import ToggleRequest, toggle_feature, MasterPauseRequest, set_master_pause
from sindhu_web.api.paper_trading import KillSwitchActivateRequest, kill_switch_activate


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    undo_stack.clear()
    yield
    undo_stack.clear()


def test_starts_with_nothing_to_undo():
    assert undo_stack.get_last_action() is None
    result = undo_stack.undo_last_action()
    assert result["ok"] is False


def test_feature_toggle_flip_is_undoable():
    toggle_feature(ToggleRequest(feature_id="strategy_lab_enabled", enabled=False))
    action = undo_stack.get_last_action()
    assert action["type"] == "feature_toggle"
    assert action["undo_data"] == {"key": "strategy_lab_enabled", "previous_value": True}

    result = undo_stack.undo_last_action()
    assert result["ok"] is True
    assert feature_toggles.get_toggles()["strategy_lab_enabled"] is True
    assert undo_stack.get_last_action() is None


def test_no_op_toggle_save_is_not_recorded_as_undoable():
    # Already True by default -- setting it to True again is not a real change.
    toggle_feature(ToggleRequest(feature_id="strategy_lab_enabled", enabled=True))
    assert undo_stack.get_last_action() is None


def test_master_pause_change_is_undoable():
    set_master_pause(MasterPauseRequest(enabled=True))
    assert undo_stack.get_last_action()["type"] == "feature_toggle"
    result = undo_stack.undo_last_action()
    assert result["ok"] is True
    assert feature_toggles.get_toggles()["master_pause_all"] is False


def test_kill_switch_activation_is_undoable(test_db):
    kill_switch_activate(KillSwitchActivateRequest(reason="test", close_positions=False))
    assert kill_switch.is_active() is True
    action = undo_stack.get_last_action()
    assert action["type"] == "kill_switch"

    result = undo_stack.undo_last_action()
    assert result["ok"] is True
    assert kill_switch.is_active() is False


def test_strategy_drawdown_pause_is_undoable(test_db):
    from unittest.mock import patch
    with patch.object(drawdown_guard.insights, "compute_streak", return_value={"type": "loss", "count": 10}):
        drawdown_guard.evaluate_strategy("strat1", "My Strategy")
    already_paused, _, _ = storage.is_strategy_paused("strat1")
    assert already_paused is True

    action = undo_stack.get_last_action()
    assert action["type"] == "strategy_drawdown_pause"
    result = undo_stack.undo_last_action()
    assert result["ok"] is True
    still_paused, _, _ = storage.is_strategy_paused("strat1")
    assert still_paused is False


def test_a_later_action_supersedes_the_earlier_undo_record():
    toggle_feature(ToggleRequest(feature_id="strategy_lab_enabled", enabled=False))
    toggle_feature(ToggleRequest(feature_id="backup_enabled", enabled=False))
    action = undo_stack.get_last_action()
    assert action["undo_data"]["key"] == "backup_enabled"


def test_endpoints_wrap_the_same_module_functions():
    toggle_feature(ToggleRequest(feature_id="strategy_lab_enabled", enabled=False))
    assert get_last_undoable_action()["action"]["type"] == "feature_toggle"
    result = undo_last_action_endpoint()
    assert result["ok"] is True
