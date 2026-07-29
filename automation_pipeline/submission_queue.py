"""Strategy Submission Queue (Task 2). Ensures multiple strategies
submitted around the same time (e.g. several AI imports finishing close
together, or several pasted at once) each actually get their full
backtest -> optimize -> re-test -> paper-trading pipeline run, instead of
the old behavior: trigger_pipeline_for_strategy() silently skipped (and
permanently lost) any strategy that tried to start while another pipeline
was already running.

Reuses the exact persistent-queue shape already proven by
ai_integration/import_queue.py (a pending/processing/completed/failed
table + a single daemon worker + an atomic claim so two workers can never
double-process the same row) but drives
automation_pipeline.pipeline.trigger_pipeline_for_strategy(), which already
has its own crash-safe checkpoint/resume via the pipeline_jobs table --
this module only adds the missing "don't lose the ones that were waiting"
piece on top of that, and never touches pipeline.py's actual stage logic.
"""

import threading
import time
import uuid
from datetime import datetime, timezone

from data_engine import storage
from data_engine.logging_setup import log as file_log
from sindhu_web.jobs import job_manager

_worker_started = False
_worker_lock = threading.Lock()
_POLL_INTERVAL_SECONDS = 2.0


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def enqueue(strategy_id, strategy_name=None, symbols=None):
    item_id = uuid.uuid4().hex[:12]
    storage.enqueue_pipeline_submission(item_id, strategy_id, strategy_name, symbols, _now_iso())
    ensure_worker_running()
    return item_id


def enqueue_batch(strategies):
    """strategies: list of dicts with strategy_id/strategy_name/symbols.
    Returns the list of queue ids in the same order they were submitted --
    that submission order is exactly the order the worker will process
    them in, since claim_next_pending_pipeline_submission() always picks
    the oldest pending row first."""
    return [enqueue(s["strategy_id"], s.get("strategy_name"), s.get("symbols")) for s in strategies]


def queue_status(limit=200):
    """Visible queue state for the dashboard: how many are waiting, and
    which one (if any) is currently running its pipeline."""
    items = storage.list_pipeline_submission_queue(limit=limit)
    pending = [i for i in items if i["status"] == "pending"]
    processing = [i for i in items if i["status"] == "processing"]
    return {
        "pending_count": len(pending),
        "current": processing[0] if processing else None,
        "items": items,
    }


def _wait_for_job(job_id):
    """Blocks (polling) until the given pipeline job reaches a terminal
    state. Checks job_manager first (fast, in-memory) and falls back to
    the durable pipeline_jobs row -- the only case that matters, since a
    server restart wipes job_manager's in-memory registry but
    resume_pipeline_jobs_on_startup() reconnects the SAME job_id to a new
    live job, and until it does, the durable row is still 'running' so
    this loop correctly keeps waiting instead of mistaking the gap for a
    finish."""
    while True:
        job = job_manager.get_job(job_id)
        if job is not None:
            if job.status != "running":
                return job.status
        else:
            row = storage.get_pipeline_job(job_id)
            if row is None or row["status"] != "running":
                return row["status"] if row else "failed"
        time.sleep(_POLL_INTERVAL_SECONDS)


def _process(item):
    if item["status"] == "processing" and item.get("job_id"):
        # Resuming a row left 'processing' by a server restart -- its
        # pipeline_jobs row (and job) has already been (or will shortly
        # be) reconnected by resume_pipeline_jobs_on_startup() using this
        # same job_id, so just wait on it rather than re-triggering.
        result_status = _wait_for_job(item["job_id"])
    else:
        from automation_pipeline.pipeline import trigger_pipeline_for_strategy
        job_id = trigger_pipeline_for_strategy(item["strategy_id"], item["strategy_name"], symbols=item.get("symbols"))
        if job_id is None:
            # Blocked by a job outside this queue (e.g. a manual
            # /api/automation/trigger verification run, or a manual
            # backtest). Leave it pending so the next worker wake retries
            # it -- never drop a submission just because it lost a race.
            storage.update_pipeline_submission(item["id"], status="pending")
            time.sleep(_POLL_INTERVAL_SECONDS)
            return
        storage.update_pipeline_submission(item["id"], job_id=job_id, status="processing", started_at=_now_iso())
        result_status = _wait_for_job(job_id)

    final_status = "completed" if result_status == "completed" else "failed"
    storage.update_pipeline_submission(item["id"], status=final_status, finished_at=_now_iso())


def _worker_loop():
    while True:
        try:
            # A stray 'processing' row (from a restart) always takes
            # priority over claiming a fresh pending one -- there is at
            # most one such row by construction, since this worker never
            # claims a second item until the first reaches a terminal
            # status.
            item = storage.get_processing_pipeline_submission() or storage.claim_next_pending_pipeline_submission()
        except Exception:
            item = None
        if not item:
            time.sleep(_POLL_INTERVAL_SECONDS)
            continue
        try:
            _process(item)
        except Exception as exc:  # pragma: no cover -- the queue worker must never die
            file_log(f"[submission-queue] item {item['id']} ({item.get('strategy_id')}) failed: {exc!r}")
            storage.update_pipeline_submission(item["id"], status="failed", error=str(exc), finished_at=_now_iso())


def ensure_worker_running():
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        threading.Thread(target=_worker_loop, daemon=True).start()
        _worker_started = True
