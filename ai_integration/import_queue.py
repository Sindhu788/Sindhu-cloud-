"""Persisted Import Queue -- pending/processing/completed/failed, with
batch import and retry. Backed by the ai_import_queue table (not the
in-memory sindhu_web.jobs.job_manager) because queued imports need to
survive being listed/retried across page loads and, unlike a single
one-shot backtest job, are naturally a growing list of many small items.

A single background daemon thread drains the queue sequentially -- one
item at a time is enough for a personal-use import queue and keeps the
"pending -> processing -> completed/failed" state machine trivially free
of races. claim_next_pending_ai_import() claims a row atomically so a
second accidental worker start (e.g. two server processes) can never
double-process the same item."""

import threading
import time
import uuid
from datetime import datetime, timezone

from data_engine import storage
from ai_integration.importer import import_document

_worker_started = False
_worker_lock = threading.Lock()
_POLL_INTERVAL_SECONDS = 1.0


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def enqueue(raw_text, title=None, source_hint=None, use_ai=True, filename=None, input_kind="text"):
    if not raw_text or not raw_text.strip():
        raise ValueError("No text/URL provided to enqueue.")
    item_id = uuid.uuid4().hex[:12]
    storage.enqueue_ai_import(item_id, title, source_hint, filename, raw_text, use_ai, _now_iso(), input_kind=input_kind)
    ensure_worker_running()
    return item_id


def enqueue_batch(items):
    """items: list of dicts with raw_text/title/source_hint/use_ai/filename/input_kind.
    Returns the list of queue ids in the same order."""
    return [
        enqueue(
            item["raw_text"], title=item.get("title"), source_hint=item.get("source_hint"),
            use_ai=item.get("use_ai", True), filename=item.get("filename"),
            input_kind=item.get("input_kind", "text"),
        )
        for item in items
    ]


def retry(item_id):
    """Re-queues a failed (or completed, if the CEO wants a re-run) item by
    resetting it back to pending -- the worker will pick it up on its next
    poll. Never re-runs an item that's currently mid-processing."""
    item = storage.get_ai_import_queue_item(item_id)
    if not item:
        raise ValueError(f"Queue item not found: {item_id}")
    if item["status"] == "processing":
        raise ValueError("Item is currently processing; cannot retry yet.")
    storage.update_ai_import_queue(
        item_id, status="pending", error_message=None, result_doc_id=None,
        ai_assisted=None, ai_provider=None, processing_time_ms=None, started_at=None, finished_at=None,
    )
    ensure_worker_running()
    return storage.get_ai_import_queue_item(item_id)


def retry_all_failed():
    failed = storage.list_ai_import_queue(status="failed", limit=1000)
    for item in failed:
        retry(item["id"])
    return len(failed)


def _process_one(item):
    started = time.time()
    storage.update_ai_import_queue(item["id"], started_at=_now_iso())
    try:
        result = import_document(
            item["raw_text"], title=item["title"], source_hint=item["source_hint"], use_ai=item["use_ai"],
            input_kind=item.get("input_kind", "text"),
        )
        elapsed_ms = int((time.time() - started) * 1000)
        if result.get("document"):
            storage.update_ai_import_queue(
                item["id"], status="completed", result_doc_id=result["document"]["id"],
                ai_assisted=result["ai_assisted"], ai_provider=result["ai_provider"],
                error_message=result.get("ai_error"), processing_time_ms=elapsed_ms, finished_at=_now_iso(),
            )
        else:
            storage.update_ai_import_queue(
                item["id"], status="failed", error_message=result.get("error") or "Import produced no document.",
                processing_time_ms=elapsed_ms, finished_at=_now_iso(),
            )
    except Exception as exc:  # pragma: no cover -- the queue worker must never die
        elapsed_ms = int((time.time() - started) * 1000)
        storage.update_ai_import_queue(
            item["id"], status="failed", error_message=str(exc),
            processing_time_ms=elapsed_ms, finished_at=_now_iso(),
        )


def _worker_loop():
    while True:
        item = None
        try:
            item = storage.claim_next_pending_ai_import()
        except Exception:
            pass
        if item:
            _process_one(item)
        else:
            time.sleep(_POLL_INTERVAL_SECONDS)


def ensure_worker_running():
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        threading.Thread(target=_worker_loop, daemon=True).start()
        _worker_started = True
