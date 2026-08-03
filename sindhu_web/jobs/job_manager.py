"""Generic background job registry. The API never blocks a request on a
download or backtest -- it starts a job here (a plain thread reusing the
exact same data_engine/backtest_engine functions the desktop app uses) and
returns immediately with a job_id the frontend polls or watches over the
WebSocket."""

import threading
import uuid
from datetime import datetime, timezone

from sindhu_web import broadcast

_jobs = {}
_lock = threading.Lock()

# Batch 7, Task 1 (memory cleanup): _jobs never had anything removing old
# entries -- every backtest/download/pipeline job ever started (including
# its full `result` dict) stayed in memory for the life of the process.
# A job's real, permanent record already lives in the database (batch_id
# lookups via backtest_batches/backtest_results) once it finishes, so this
# in-memory registry only needs to cover "recent enough to still be
# polled or shown in Recent Activity" -- capped rather than unbounded.
# Running jobs are NEVER pruned, no matter how many are in flight.
MAX_RETAINED_JOBS = 200


def _prune_finished_locked():
    """Must be called with _lock already held. Evicts the oldest FINISHED
    (non-running) jobs once total count exceeds MAX_RETAINED_JOBS -- a
    job still running is always kept regardless of how far over the cap
    that pushes the total."""
    overflow = len(_jobs) - MAX_RETAINED_JOBS
    if overflow <= 0:
        return
    finished = sorted(
        (j for j in _jobs.values() if j.status != "running"),
        key=lambda j: j.finished_at or j.started_at,
    )
    for j in finished[:overflow]:
        del _jobs[j.id]


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


class Job:
    def __init__(self, job_id, kind, control=None):
        self.id = job_id
        self.kind = kind
        self.status = "running"
        self.control = control
        self.started_at = _now_iso()
        self.finished_at = None
        self.result = None
        self.error = None
        self.progress = {}

    def to_dict(self):
        return {
            "id": self.id, "kind": self.kind, "status": self.status,
            "started_at": self.started_at, "finished_at": self.finished_at,
            "error": self.error, "progress": self.progress, "result": self.result,
        }


def create_job(kind, target, control=None, args=(), kwargs=None, job_id=None):
    kwargs = kwargs or {}
    job_id = job_id or uuid.uuid4().hex[:12]
    job = Job(job_id, kind, control=control)

    def _runner():
        try:
            job.result = target(*args, **kwargs)
            job.status = "stopped" if (control and control.should_stop()) else "completed"
        except Exception as e:
            job.status = "error"
            job.error = repr(e)
        finally:
            job.finished_at = _now_iso()
            with _lock:
                _prune_finished_locked()
            broadcast.publish({
                "channel": "job", "job_id": job_id, "event": "finished",
                "status": job.status, "kind": kind,
                "batch_id": (job.result or {}).get("batch_id") if isinstance(job.result, dict) else None,
            })

    with _lock:
        _jobs[job_id] = job
        _prune_finished_locked()
    threading.Thread(target=_runner, daemon=True).start()
    broadcast.publish({"channel": "job", "job_id": job_id, "event": "started", "kind": kind})
    return job_id


def get_job(job_id):
    with _lock:
        return _jobs.get(job_id)


def get_running_job_of_kind(kind):
    """First still-running job of this kind, or None. Used to enforce
    "only one backtest at a time" without touching any other job kind
    (downloads etc. are unaffected)."""
    with _lock:
        for job in _jobs.values():
            if job.kind == kind and job.status == "running":
                return job
    return None


def list_jobs():
    with _lock:
        return list(_jobs.values())


def update_progress(job_id, **fields):
    job = get_job(job_id)
    if job:
        job.progress.update(fields)
        broadcast.publish({"channel": "progress", "job_id": job_id, **job.progress})


def make_log_fn(job_id):
    def _log(message):
        from data_engine.logging_setup import log as file_log
        file_log(message)
        broadcast.publish({"channel": "log", "job_id": job_id, "message": message})
    return _log
