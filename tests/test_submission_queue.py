"""Tests for Task 2's strategy submission queue
(automation_pipeline/submission_queue.py) -- the queue that makes sure
several strategies submitted close together each get their full pipeline
run, one at a time, instead of the pre-Task-2 behavior where
trigger_pipeline_for_strategy() silently skipped (and lost) anything past
the first. Reuses the same test_db fixture (fresh isolated SQLite) as the
rest of the suite.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from data_engine import storage
from automation_pipeline import submission_queue


@pytest.fixture(autouse=True)
def _no_real_worker_thread(monkeypatch):
    """enqueue()/enqueue_batch() normally start a real daemon worker
    thread (ensure_worker_running()) -- exactly what production wants, but
    fatal for test isolation: that thread is a module-level global that
    outlives the test, keeps polling storage.get_conn() against whatever
    DB_PATH test_db monkeypatches next, and silently claims/processes rows
    from LATER tests using the real (unmocked) trigger_pipeline_for_strategy.
    Every test below exercises _process()/storage helpers directly instead,
    so the thread is never needed here."""
    monkeypatch.setattr(submission_queue, "ensure_worker_running", lambda: None)


def test_enqueue_and_claim_storage_roundtrip(test_db):
    item_id = "abc123"
    storage.enqueue_pipeline_submission(item_id, "strat1", "Strategy One", None, "2026-01-01T00:00:00+00:00")
    item = storage.get_pipeline_submission(item_id)
    assert item["status"] == "pending"
    assert item["strategy_id"] == "strat1"
    assert item["symbols"] is None

    claimed = storage.claim_next_pending_pipeline_submission()
    assert claimed["id"] == item_id
    assert storage.get_pipeline_submission(item_id)["status"] == "processing"

    assert storage.claim_next_pending_pipeline_submission() is None


def test_claim_returns_oldest_first(test_db):
    storage.enqueue_pipeline_submission("first", "s1", "S1", None, "2026-01-01T00:00:00+00:00")
    storage.enqueue_pipeline_submission("second", "s2", "S2", None, "2026-01-01T00:00:01+00:00")
    claimed = storage.claim_next_pending_pipeline_submission()
    assert claimed["id"] == "first"


def test_enqueue_batch_preserves_submission_order(test_db):
    ids = submission_queue.enqueue_batch([
        {"strategy_id": "s1", "strategy_name": "S1"},
        {"strategy_id": "s2", "strategy_name": "S2"},
        {"strategy_id": "s3", "strategy_name": "S3"},
    ])
    items = storage.list_pipeline_submission_queue()
    assert [i["strategy_id"] for i in items] == ["s1", "s2", "s3"]
    assert len(ids) == 3


def test_queue_status_reports_pending_count_and_current(test_db):
    storage.enqueue_pipeline_submission("a", "s1", "S1", None, "2026-01-01T00:00:00+00:00")
    storage.enqueue_pipeline_submission("b", "s2", "S2", None, "2026-01-01T00:00:01+00:00")
    storage.update_pipeline_submission("a", status="processing")
    status = submission_queue.queue_status()
    assert status["pending_count"] == 1
    assert status["current"]["id"] == "a"


def test_process_marks_completed_when_pipeline_job_completes(test_db):
    storage.enqueue_pipeline_submission("item1", "strat1", "Strategy One", None, "2026-01-01T00:00:00+00:00")
    item = storage.claim_next_pending_pipeline_submission()

    fake_job = SimpleNamespace(status="completed")
    with patch("automation_pipeline.pipeline.trigger_pipeline_for_strategy", return_value="job1") as mock_trigger, \
         patch("automation_pipeline.submission_queue.job_manager.get_job", return_value=fake_job):
        submission_queue._process(item)
        mock_trigger.assert_called_once_with("strat1", "Strategy One", symbols=None)

    final = storage.get_pipeline_submission("item1")
    assert final["status"] == "completed"
    assert final["job_id"] == "job1"


def test_process_marks_failed_when_pipeline_job_errors(test_db):
    storage.enqueue_pipeline_submission("item2", "strat2", "Strategy Two", None, "2026-01-01T00:00:00+00:00")
    item = storage.claim_next_pending_pipeline_submission()

    fake_job = SimpleNamespace(status="error")
    with patch("automation_pipeline.pipeline.trigger_pipeline_for_strategy", return_value="job2"), \
         patch("automation_pipeline.submission_queue.job_manager.get_job", return_value=fake_job):
        submission_queue._process(item)

    final = storage.get_pipeline_submission("item2")
    assert final["status"] == "failed"


def test_process_leaves_item_pending_when_blocked_by_outside_job(test_db):
    """trigger_pipeline_for_strategy() returns None when a pipeline/backtest
    is already running outside this queue -- the item must go back to
    'pending' (never lost) so the next worker wake retries it."""
    storage.enqueue_pipeline_submission("item3", "strat3", "Strategy Three", None, "2026-01-01T00:00:00+00:00")
    item = storage.claim_next_pending_pipeline_submission()

    with patch("automation_pipeline.pipeline.trigger_pipeline_for_strategy", return_value=None), \
         patch("automation_pipeline.submission_queue.time.sleep"):
        submission_queue._process(item)

    final = storage.get_pipeline_submission("item3")
    assert final["status"] == "pending"


def test_resume_after_restart_waits_on_existing_job_without_retriggering(test_db):
    """A row left 'processing' with a job_id (simulating a server restart
    mid-run) must wait on that SAME job and never call
    trigger_pipeline_for_strategy again -- doing so would start a second,
    duplicate pipeline run for the same strategy."""
    storage.enqueue_pipeline_submission("item4", "strat4", "Strategy Four", None, "2026-01-01T00:00:00+00:00")
    storage.update_pipeline_submission("item4", status="processing", job_id="resumed-job")
    item = storage.get_pipeline_submission("item4")

    fake_job = SimpleNamespace(status="completed")
    with patch("automation_pipeline.pipeline.trigger_pipeline_for_strategy") as mock_trigger, \
         patch("automation_pipeline.submission_queue.job_manager.get_job", return_value=fake_job):
        submission_queue._process(item)
        mock_trigger.assert_not_called()

    final = storage.get_pipeline_submission("item4")
    assert final["status"] == "completed"
    assert final["job_id"] == "resumed-job"


def test_get_processing_pipeline_submission_finds_stuck_row(test_db):
    storage.enqueue_pipeline_submission("item5", "strat5", "Strategy Five", None, "2026-01-01T00:00:00+00:00")
    storage.update_pipeline_submission("item5", status="processing", job_id="j5")
    stuck = storage.get_processing_pipeline_submission()
    assert stuck["id"] == "item5"
