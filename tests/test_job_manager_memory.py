"""Batch 7, Task 1 (memory cleanup): sindhu_web/jobs/job_manager.py's
_jobs registry used to grow forever -- every job ever started (including
its full `result` dict) stayed in memory for the life of the process. A
finished job's real, permanent record already lives in the database
(backtest_batches/backtest_results via batch_id), so the in-memory
registry only needs to cover "recent enough to still be polled or shown
in Recent Activity" -- capped at MAX_RETAINED_JOBS, oldest FINISHED jobs
evicted first, a job still RUNNING is never evicted regardless of count.
"""

import pytest

from sindhu_web.jobs import job_manager


@pytest.fixture(autouse=True)
def isolated_jobs(monkeypatch):
    monkeypatch.setattr(job_manager, "_jobs", {})
    yield


def _make_job(job_id, status, finished_at):
    j = job_manager.Job(job_id, "test_kind")
    j.status = status
    j.finished_at = finished_at
    return j


def test_prune_evicts_oldest_finished_jobs_once_over_cap():
    for i in range(job_manager.MAX_RETAINED_JOBS + 10):
        job_manager._jobs[f"j{i}"] = _make_job(f"j{i}", "completed", f"2026-01-01T00:{i:02d}:00+00:00")
    with job_manager._lock:
        job_manager._prune_finished_locked()
    assert len(job_manager._jobs) == job_manager.MAX_RETAINED_JOBS
    assert "j0" not in job_manager._jobs
    assert f"j{job_manager.MAX_RETAINED_JOBS + 9}" in job_manager._jobs


def test_running_jobs_are_never_pruned_even_over_cap():
    for i in range(job_manager.MAX_RETAINED_JOBS + 10):
        job_manager._jobs[f"r{i}"] = _make_job(f"r{i}", "running", None)
    with job_manager._lock:
        job_manager._prune_finished_locked()
    assert len(job_manager._jobs) == job_manager.MAX_RETAINED_JOBS + 10  # untouched, all still running


def test_prune_keeps_running_jobs_and_evicts_only_finished_ones_when_mixed():
    for i in range(10):
        job_manager._jobs[f"r{i}"] = _make_job(f"r{i}", "running", None)
    for i in range(job_manager.MAX_RETAINED_JOBS):
        job_manager._jobs[f"f{i}"] = _make_job(f"f{i}", "completed", f"2026-01-01T00:{i % 60:02d}:00+00:00")
    with job_manager._lock:
        job_manager._prune_finished_locked()
    # 10 running + cap finished = 10 over cap -> exactly 10 oldest finished evicted
    assert sum(1 for j in job_manager._jobs.values() if j.status == "running") == 10
    assert len(job_manager._jobs) == 10 + job_manager.MAX_RETAINED_JOBS - 10


def test_below_cap_nothing_is_pruned():
    for i in range(5):
        job_manager._jobs[f"j{i}"] = _make_job(f"j{i}", "completed", f"2026-01-01T00:0{i}:00+00:00")
    with job_manager._lock:
        job_manager._prune_finished_locked()
    assert len(job_manager._jobs) == 5


def test_create_job_prunes_after_a_flood_of_completed_jobs():
    """End-to-end via the real create_job()/thread path, not just the
    internal prune function directly."""
    for i in range(job_manager.MAX_RETAINED_JOBS + 20):
        job_id = job_manager.create_job("test_kind", lambda: {"ok": True}, job_id=f"flood{i}")
        job = job_manager.get_job(job_id)
        # target is trivial and synchronous-fast, but the runner thread is
        # still async -- wait for it to actually finish before moving on.
        for _ in range(200):
            if job.status != "running":
                break
            import time
            time.sleep(0.005)
    assert len(job_manager._jobs) <= job_manager.MAX_RETAINED_JOBS
