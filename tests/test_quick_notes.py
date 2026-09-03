"""Grand Feature Expansion, Phase 4 Feature 21: Quick Note Box -- an
instant, unstructured scratch-pad, distinct from user_feedback (a
structured type+status request/backlog workflow)."""

from datetime import datetime, timezone

from data_engine import storage
from sindhu_web.api.project_status import QuickNoteCreate, create_quick_note, get_quick_notes, remove_quick_note


def _now():
    return datetime.now(timezone.utc).isoformat()


def test_no_notes_yet_returns_empty_list(test_db):
    assert storage.list_quick_notes() == []


def test_create_and_list_note(test_db):
    note_id = storage.create_quick_note("Check the coin blacklist tomorrow", _now())
    notes = storage.list_quick_notes()
    assert len(notes) == 1
    assert notes[0]["id"] == note_id
    assert notes[0]["content"] == "Check the coin blacklist tomorrow"


def test_most_recent_note_listed_first(test_db):
    storage.create_quick_note("First", _now())
    storage.create_quick_note("Second", _now())
    notes = storage.list_quick_notes()
    assert notes[0]["content"] == "Second"
    assert notes[1]["content"] == "First"


def test_delete_note_removes_it(test_db):
    note_id = storage.create_quick_note("Temporary", _now())
    storage.delete_quick_note(note_id)
    assert storage.list_quick_notes() == []


def test_endpoint_create_rejects_empty_content(test_db):
    result = create_quick_note(QuickNoteCreate(content="   "))
    assert result["ok"] is False
    assert storage.list_quick_notes() == []


def test_endpoint_create_strips_and_saves(test_db):
    result = create_quick_note(QuickNoteCreate(content="  Remember to test the alert rule  "))
    assert result["ok"] is True
    notes = get_quick_notes()["notes"]
    assert notes[0]["content"] == "Remember to test the alert rule"


def test_endpoint_delete(test_db):
    create_quick_note(QuickNoteCreate(content="To be deleted"))
    note_id = get_quick_notes()["notes"][0]["id"]
    remove_quick_note(note_id)
    assert get_quick_notes()["notes"] == []
