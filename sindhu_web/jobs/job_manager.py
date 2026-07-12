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
            broadcast.publish({
                "channel": "job", "job_id": job_id, "event": "finished",
                "status": job.status, "kind": kind,
                "batch_id": (job.result or {}).get("batch_id") if isinstance(job.result, dict) else None,
            })

    with _lock:
        _jobs[job_id] = job
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
