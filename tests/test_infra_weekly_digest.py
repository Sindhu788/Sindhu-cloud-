"""Grand Feature Expansion, Phase 7 Feature 10: Automated Weekly Digest
(sindhu_web/api/infra_weekly_digest.py) -- a weekly SYSTEM/INFRASTRUCTURE
health digest (backups, incidents, disk/database size), deliberately
distinct content from the 3 report types that already exist:
paper_trading.weekly_report (trading performance), evolution_engine.
weekly_review (tuning/evolution activity), paper_trading.monthly_report
(30-day trading). Mirrors weekly_report.py's generate/gate/scheduler/
Telegram-send shape.
"""

from datetime import datetime, timedelta, timezone

import pytest

from data_engine import config as base_config, feature_toggles, storage
from sindhu_web.api import backup, infra_weekly_digest


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch, test_db):
    # Same real isolation gap discovered while building Weekly Auto-
    # Snapshot: backup.py's DB_PATH is bound at import time from
    # data_engine.paths, unaffected by the test_db fixture's
    # storage.DB_PATH patch.
    monkeypatch.setattr(backup, "DB_PATH", test_db)
    monkeypatch.setattr(backup, "_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def test_generate_with_no_activity(test_db):
    result = infra_weekly_digest.generate_infra_weekly_digest()
    assert "0 rolling backup(s)" in result["report_text"]
    assert "0 opened, 0 resolved" in result["report_text"]
    assert result["report_data"]["incidents_still_open"] == 0


def test_generate_counts_a_real_backup_made_this_week(test_db):
    backup.create_backup()
    result = infra_weekly_digest.generate_infra_weekly_digest()
    assert result["report_data"]["backups_this_week"] == 1


def test_generate_reports_open_incidents(test_db):
    now_iso = datetime.now(timezone.utc).isoformat()
    storage.create_incident("inc1", "Test Incident", "problem", "tester", "high", now_iso)
    result = infra_weekly_digest.generate_infra_weekly_digest()
    assert result["report_data"]["incidents_opened"] == 1
    assert result["report_data"]["incidents_still_open"] == 1
    assert "Test Incident" in result["report_text"]


def test_generate_reports_resolved_incidents(test_db):
    now_iso = datetime.now(timezone.utc).isoformat()
    storage.create_incident("inc1", "Test Incident", "problem", "tester", "high", now_iso)
    storage.update_incident("inc1", now_iso, status="resolved", resolved_at=now_iso)
    result = infra_weekly_digest.generate_infra_weekly_digest()
    assert result["report_data"]["incidents_resolved"] == 1
    assert result["report_data"]["incidents_still_open"] == 0


def test_generate_persists_a_permanent_row(test_db):
    infra_weekly_digest.generate_infra_weekly_digest()
    assert len(storage.list_infra_weekly_digests()) == 1


def test_maybe_generate_respects_the_7_day_gate(test_db):
    first = infra_weekly_digest.maybe_generate_infra_weekly_digest()
    assert first is not None
    second = infra_weekly_digest.maybe_generate_infra_weekly_digest()
    assert second is None
    assert len(storage.list_infra_weekly_digests()) == 1


def test_maybe_generate_returns_none_when_disabled(test_db):
    feature_toggles.set_toggle("infra_weekly_digest_enabled", False)
    result = infra_weekly_digest.maybe_generate_infra_weekly_digest()
    assert result is None
    assert storage.list_infra_weekly_digests() == []


def test_gate_reopens_after_7_days(test_db):
    infra_weekly_digest.generate_infra_weekly_digest()
    old_created_at = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    with storage.get_conn() as conn:
        conn.execute("UPDATE infra_weekly_digests SET created_at=?", (old_created_at,))
    result = infra_weekly_digest.maybe_generate_infra_weekly_digest()
    assert result is not None
    assert len(storage.list_infra_weekly_digests()) == 2


def test_endpoint_lists_and_generates(test_db):
    from sindhu_web.api.infra_weekly_digest import get_infra_weekly_digests, generate_infra_weekly_digest_now

    assert get_infra_weekly_digests()["digests"] == []
    generate_infra_weekly_digest_now()
    assert len(get_infra_weekly_digests()["digests"]) == 1
