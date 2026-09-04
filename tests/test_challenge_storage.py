"""Master Task 3, Phase 2.9: data_engine.storage's new multi-challenge
table (challenges) -- independent of paper_trading.challenge_mode's
original single-challenge JSON/cloud_setting, which stays untouched.
"""

from datetime import datetime, timezone

from data_engine import storage


def _now():
    return datetime.now(timezone.utc).isoformat()


def test_create_and_get_round_trip(test_db):
    storage.create_challenge("c1", "My Challenge", 1000.0, 2000.0, "custom", 30, _now(), _now())
    c = storage.get_challenge("c1")
    assert c["label"] == "My Challenge"
    assert c["start_amount"] == 1000.0
    assert c["target_amount"] == 2000.0
    assert c["archived"] is False
    assert c["compounding"] is True


def test_get_unknown_challenge_returns_none(test_db):
    assert storage.get_challenge("nope") is None


def test_list_challenges_excludes_archived_by_default(test_db):
    storage.create_challenge("c1", "A", 1000.0, 2000.0, "custom", 30, _now(), _now())
    storage.create_challenge("c2", "B", 1000.0, 1500.0, "weekly", 7, _now(), _now())
    storage.archive_challenge("c2", _now())

    active = storage.list_challenges()
    assert [c["id"] for c in active] == ["c1"]

    everything = storage.list_challenges(include_archived=True)
    assert {c["id"] for c in everything} == {"c1", "c2"}


def test_update_challenge_extends_days_without_resetting_started_at(test_db):
    started = _now()
    storage.create_challenge("c1", "A", 1000.0, 2000.0, "custom", 30, started, _now())
    storage.update_challenge("c1", _now(), days=45)
    c = storage.get_challenge("c1")
    assert c["days"] == 45
    assert c["started_at"] == started  # unchanged -- progress is not reset


def test_update_challenge_normalizes_boolean_fields(test_db):
    storage.create_challenge("c1", "A", 1000.0, 2000.0, "custom", 30, _now(), _now(), compounding=True)
    storage.update_challenge("c1", _now(), compounding=False, telegram_report_enabled=True)
    c = storage.get_challenge("c1")
    assert c["compounding"] is False
    assert c["telegram_report_enabled"] is True


def test_update_challenge_rejects_unknown_field(test_db):
    storage.create_challenge("c1", "A", 1000.0, 2000.0, "custom", 30, _now(), _now())
    try:
        storage.update_challenge("c1", _now(), not_a_real_field=1)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_achievability_snapshots_round_trip_and_filter_by_since(test_db):
    storage.create_challenge("c1", "A", 1000.0, 2000.0, "custom", 30, _now(), _now())
    storage.record_challenge_achievability_snapshot("c1", 72.5, "2026-01-01T00:00:00+00:00")
    storage.record_challenge_achievability_snapshot("c1", 80.0, "2026-01-05T00:00:00+00:00")

    all_snaps = storage.list_challenge_achievability_snapshots("c1")
    assert [s["achievability_score"] for s in all_snaps] == [72.5, 80.0]

    recent = storage.list_challenge_achievability_snapshots("c1", since_iso="2026-01-03T00:00:00+00:00")
    assert [s["achievability_score"] for s in recent] == [80.0]
