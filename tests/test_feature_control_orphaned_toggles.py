"""5-Phase Improvement Batch, Phase 4: strategy_lab_enabled and
self_learning_engine_enabled existed in data_engine.feature_toggles.
DEFAULTS with a real gate check (paper_trading/strategy_lab.py,
self_learning_engine/discovery_cycle.py) but had no Control Center entry
and no toggle endpoint -- the only way to flip them was a direct Python
call. This confirms both are now reachable through the SAME existing
/api/feature-control/toggle endpoint every other feature already uses.
"""

from data_engine import config as base_config, feature_toggles
from sindhu_web.api.feature_control import get_state, toggle_feature, ToggleRequest


def test_strategy_lab_toggle_is_reachable_through_the_control_endpoint(test_db, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(test_db).rsplit("test_sindhu.db", 1)[0])
    result = toggle_feature(ToggleRequest(feature_id="strategy_lab_enabled", enabled=False))
    assert result["ok"] is True
    assert feature_toggles.get_toggles()["strategy_lab_enabled"] is False


def test_self_learning_engine_toggle_is_reachable_through_the_control_endpoint(test_db, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(test_db).rsplit("test_sindhu.db", 1)[0])
    result = toggle_feature(ToggleRequest(feature_id="self_learning_engine_enabled", enabled=False))
    assert result["ok"] is True
    assert feature_toggles.get_toggles()["self_learning_engine_enabled"] is False


def test_both_orphaned_toggles_now_appear_in_control_center_state(test_db, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(test_db).rsplit("test_sindhu.db", 1)[0])
    state = get_state()
    ids = {f["id"] for f in state["features"]}
    assert "strategy_lab_enabled" in ids
    assert "self_learning_engine_enabled" in ids
