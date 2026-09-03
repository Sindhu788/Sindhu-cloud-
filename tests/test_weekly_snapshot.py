"""Grand Feature Expansion, Phase 7 Feature 3: Weekly Auto-Snapshot
(sindhu_web/api/weekly_snapshot.py) -- a genuinely weekly-cadence database
snapshot, distinct from the existing rolling 6-hourly backup (whose
retention has no week-boundary awareness -- 10 backups at the default
6-hour interval is only ~2.5 days). Reuses backup._hot_copy() for the
actual copy mechanism.
"""

from datetime import datetime, timedelta, timezone

import pytest

from sindhu_web.api import backup, weekly_snapshot


@pytest.fixture(autouse=True)
def isolated_snapshot_dir(tmp_path, monkeypatch, test_db):
    # backup._hot_copy() reads from backup.py's OWN module-level DB_PATH
    # (imported directly from data_engine.paths at module-load time), which
    # the test_db fixture's storage.DB_PATH patch does NOT touch -- without
    # patching this too, _hot_copy would silently hot-copy the REAL local
    # database on every test run instead of the isolated test one.
    monkeypatch.setattr(backup, "DB_PATH", test_db)
    monkeypatch.setattr(weekly_snapshot, "_SNAPSHOT_DIR", str(tmp_path / "weekly_snapshots"))
    yield


def test_no_snapshots_yet(test_db):
    assert weekly_snapshot.list_weekly_snapshots() == []


def test_create_weekly_snapshot_creates_a_real_file(test_db):
    name = weekly_snapshot.create_weekly_snapshot()
    assert name.startswith("sindhu_weekly_")
    snapshots = weekly_snapshot.list_weekly_snapshots()
    assert len(snapshots) == 1
    assert snapshots[0]["name"] == name
    assert snapshots[0]["size_bytes"] > 0


def test_prune_keeps_only_the_last_keep_last_snapshots(test_db, monkeypatch):
    monkeypatch.setattr(weekly_snapshot, "KEEP_LAST", 2)
    # _now_stamp() has 1-second resolution -- real usage is always naturally
    # spaced (the 7-day gate, or a human clicking "Create Now" more than a
    # second apart), but a tight test loop needs distinct stamps forced.
    counter = [0]

    def fake_stamp():
        counter[0] += 1
        return f"2026010{counter[0]}_000000"

    monkeypatch.setattr(weekly_snapshot, "_now_stamp", fake_stamp)
    for _ in range(4):
        weekly_snapshot.create_weekly_snapshot()
    assert len(weekly_snapshot.list_weekly_snapshots()) == 2


def test_maybe_create_respects_the_7_day_gate(test_db):
    first = weekly_snapshot.maybe_create_weekly_snapshot()
    assert first is not None
    second = weekly_snapshot.maybe_create_weekly_snapshot()
    assert second is None  # too soon
    assert len(weekly_snapshot.list_weekly_snapshots()) == 1


def test_gate_reopens_after_7_days(test_db, monkeypatch):
    counter = [0]

    def fake_stamp():
        counter[0] += 1
        return f"2026010{counter[0]}_000000"

    monkeypatch.setattr(weekly_snapshot, "_now_stamp", fake_stamp)
    weekly_snapshot.create_weekly_snapshot()
    old_time = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    monkeypatch.setattr(weekly_snapshot, "_latest_snapshot_time", lambda: old_time)
    result = weekly_snapshot.maybe_create_weekly_snapshot()
    assert result is not None
    assert len(weekly_snapshot.list_weekly_snapshots()) == 2


def test_endpoint_list_and_create_now(test_db):
    assert weekly_snapshot.get_weekly_snapshots()["snapshots"] == []
    result = weekly_snapshot.create_weekly_snapshot_now()
    assert result["snapshot"].startswith("sindhu_weekly_")
    assert len(weekly_snapshot.get_weekly_snapshots()["snapshots"]) == 1
