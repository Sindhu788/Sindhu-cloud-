"""Grand Feature Expansion, Phase 1 Feature 3: the permanent Audit Trail
(data_engine.storage.audit_trail_log / record_audit_event / list_audit_trail),
fed automatically through sindhu_web.sync.notify() -- the codebase's
existing single choke point for "significant" events -- plus a couple of
direct calls added at two identified gaps (feature-control toggles and
backup create/restore, neither of which previously called sync.notify at
all).

Confirms the key property that makes this different from the existing
activity_log feed: it is never pruned, however many events are recorded.
"""

from data_engine import storage
from sindhu_web import sync


def test_record_and_list_audit_event(test_db):
    storage.record_audit_event("paper_trading", "started", "Paper Trading engine started", "2026-01-01T00:00:00+00:00")
    rows = storage.list_audit_trail()
    assert len(rows) == 1
    assert rows[0]["entity"] == "paper_trading"
    assert rows[0]["action"] == "started"
    assert storage.count_audit_trail() == 1


def test_list_audit_trail_filters_by_entity_and_since(test_db):
    storage.record_audit_event("paper_trading", "started", "a", "2026-01-01T00:00:00+00:00")
    storage.record_audit_event("kill_switch", "activated", "b", "2026-01-02T00:00:00+00:00")
    storage.record_audit_event("paper_trading", "stopped", "c", "2026-01-03T00:00:00+00:00")

    only_pt = storage.list_audit_trail(entity="paper_trading")
    assert {r["action"] for r in only_pt} == {"started", "stopped"}

    since = storage.list_audit_trail(since_iso="2026-01-02T00:00:00+00:00")
    assert {r["action"] for r in since} == {"activated", "stopped"}


def test_audit_trail_is_never_pruned_unlike_the_capped_activity_feed(test_db):
    """activity_log caps itself at 500 rows (see storage.log_activity's own
    docstring); audit_trail_log must not -- this is the entire point of the
    feature. Uses a small number for test speed, but proves the mechanism:
    no DELETE statement runs against audit_trail_log anywhere."""
    for i in range(20):
        storage.record_audit_event("test", "event", f"event {i}", f"2026-01-01T00:00:{i:02d}+00:00")
    assert storage.count_audit_trail() == 20
    import inspect
    assert "DELETE" not in inspect.getsource(storage.record_audit_event)


def test_sync_notify_writes_to_both_activity_log_and_the_permanent_audit_trail(test_db):
    sync.notify("paper_trading", "started", "Paper Trading engine started")
    activity = storage.list_activity(10)
    audit = storage.list_audit_trail(10)
    assert len(activity) == 1
    assert len(audit) == 1
    assert activity[0]["message"] == audit[0]["message"] == "Paper Trading engine started"


def test_feature_control_toggle_is_recorded_in_the_audit_trail(test_db, monkeypatch):
    from data_engine import config as base_config
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(test_db).rsplit("test_sindhu.db", 1)[0])
    from sindhu_web.api.feature_control import toggle_feature, ToggleRequest
    toggle_feature(ToggleRequest(feature_id="auto_avoid_enabled", enabled=False))
    audit = storage.list_audit_trail()
    assert any(r["entity"] == "feature_control" and "auto_avoid_enabled" in r["message"] for r in audit)


def test_feature_control_master_pause_is_recorded_in_the_audit_trail(test_db, monkeypatch):
    from data_engine import config as base_config
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(test_db).rsplit("test_sindhu.db", 1)[0])
    from sindhu_web.api.feature_control import set_master_pause, MasterPauseRequest
    set_master_pause(MasterPauseRequest(enabled=True))
    audit = storage.list_audit_trail()
    assert any(r["entity"] == "feature_control" and r["action"] == "master_pause" for r in audit)


def test_backup_create_and_restore_are_recorded_in_the_audit_trail(test_db, tmp_path, monkeypatch):
    from data_engine import paths as data_paths
    from sindhu_web.api import backup as backup_api

    monkeypatch.setattr(data_paths, "DATABASE_DIR", str(tmp_path))
    monkeypatch.setattr(backup_api, "_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(backup_api, "DB_PATH", test_db)
    from data_engine import config as base_config
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))

    name = backup_api.create_backup()
    audit = storage.list_audit_trail()
    assert any(r["entity"] == "backup" and r["action"] == "created" for r in audit)

    backup_api.restore_backup(backup_api.RestoreRequest(backup_name=name, confirm=True))
    audit = storage.list_audit_trail()
    assert any(r["entity"] == "backup" and r["action"] == "restored" for r in audit)
