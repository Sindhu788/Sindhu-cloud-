"""Master Task 3, Phase 1: API surface for the Self-Learning Engine.
Local-only (like backtesting.py/evolution.py) -- never mounted on the
lightweight cloud runner (cloud_runtime/app.py), since every discovery
cycle needs the full local historical database and backtest pipeline.
"""

import threading

from fastapi import APIRouter

from data_engine import storage
from data_engine.logging_setup import log
from self_learning_engine import combination_scorer, discovery_cycle

router = APIRouter()

_run_lock = threading.Lock()
_run_in_progress = False


@router.get("/api/self-learning/status")
def get_status():
    latest = storage.get_latest_self_learning_cycle()
    return {
        "run_in_progress": _run_in_progress,
        "would_run_now": discovery_cycle.should_run_new_cycle(),
        "latest_cycle": latest,
    }


@router.get("/api/self-learning/cycles")
def get_cycles(limit: int = 20):
    return {"cycles": storage.list_self_learning_cycles(limit=limit)}


@router.get("/api/self-learning/attempts")
def get_attempts(limit: int = 200):
    return {"attempts": storage.list_self_learning_attempts(limit=limit)}


@router.get("/api/self-learning/combination-scores")
def get_combination_scores():
    """Live view into the same real system-wide evidence the engine itself
    scores combinations from (Phase 1.1/1.3) -- lets the CEO see what the
    engine currently thinks is worth trying, without waiting for a cycle."""
    return {"combinations": combination_scorer.score_combinations()}


@router.post("/api/self-learning/run-now")
def run_now():
    """Fire-and-forget: a real discovery cycle runs two full backtests and
    can take a long while, far past any reasonable HTTP request timeout --
    same 'kick off a background thread, poll /status or /cycles for the
    result' shape as every other long-running job trigger in this project.
    Refuses to start a second cycle while one is already running."""
    global _run_in_progress
    with _run_lock:
        if _run_in_progress:
            return {"started": False, "reason": "a discovery cycle is already running"}
        _run_in_progress = True

    def _run():
        global _run_in_progress
        try:
            result = discovery_cycle.run_discovery_cycle(force=True)
            log(f"[self-learning] manual discovery cycle finished: {result.get('status')}")
        except Exception as e:
            log(f"[self-learning] manual discovery cycle failed: {e!r}")
        finally:
            with _run_lock:
                _run_in_progress = False

    threading.Thread(target=_run, daemon=True).start()
    return {"started": True}


def start_self_learning_scheduler_thread():
    """Runs once at server startup; checks periodically whether a new
    weekly cycle is due -- same shape as infra_weekly_digest.py's own
    scheduler. Checked every 6 hours (not more often): the weekly gate
    inside run_discovery_cycle already prevents over-running, this interval
    just bounds how late a due cycle could start after the 7 days elapse."""
    import time

    global _run_in_progress

    def _loop():
        global _run_in_progress
        while True:
            try:
                if discovery_cycle.should_run_new_cycle():
                    with _run_lock:
                        if _run_in_progress:
                            continue
                        _run_in_progress = True
                    try:
                        result = discovery_cycle.run_discovery_cycle()
                        log(f"[self-learning] scheduled discovery cycle finished: {result.get('status')}")
                    finally:
                        with _run_lock:
                            _run_in_progress = False
            except Exception as e:
                log(f"[self-learning] scheduled discovery cycle failed: {e!r}")
            time.sleep(6 * 3600)

    threading.Thread(target=_loop, daemon=True).start()
