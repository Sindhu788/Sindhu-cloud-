"""A.12 -- Evolution Engine orchestrator. The single background loop that
ties Governor (A.3) + Generation Manager (A.4/A.5) + Mutator (A.2) +
Champion Engine (A.7) together into one continuously-running process.

Architecture deliberately mirrors two systems that already exist and are
already verified, rather than inventing a third pattern:
  - The background loop itself is a daemon thread exactly like
    paper_trading.engine._loop (poll, sleep tick_interval_seconds, repeat).
  - Checkpoint/resume is the exact same shape as automation_pipeline.pipeline:
    an evolution_jobs row (mirrors pipeline_jobs) holds status/stage/
    checkpoint_json, and any row still 'running' at server boot means the
    process died mid-tick -- resume_evolution_jobs_on_startup() picks it
    back up, called from sindhu_web/server.py's lifespan exactly where
    resume_pipeline_jobs_on_startup() already is.
"""

import threading
import time
from datetime import datetime, timezone

from data_engine import storage
from evolution_engine.governor import Governor
from evolution_engine import mutator, champion

DEFAULT_TICK_INTERVAL_SECONDS = 300  # one evolution tick every 5 minutes


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


class EvolutionEngine:
    def __init__(self, tick_interval_seconds=DEFAULT_TICK_INTERVAL_SECONDS, governor=None, log=print):
        self.tick_interval_seconds = tick_interval_seconds
        self.governor = governor or Governor()
        self._log = log
        self._thread = None
        self._stop_flag = threading.Event()
        self._running = False
        self._lock = threading.Lock()
        self.job_id = None
        self._checkpoint_data = {}

    def is_running(self):
        with self._lock:
            return self._running

    def start(self, resume_job=None):
        with self._lock:
            if self._running:
                return False
            self._stop_flag.clear()
            self.job_id = (resume_job or {}).get("job_id") or f"evo_{int(time.time() * 1000)}"
            now = _now_iso()
            if resume_job:
                self._checkpoint_data = dict(resume_job.get("checkpoint") or {})
                storage.update_evolution_job(self.job_id, now, status="running", stage="resuming")
            else:
                self._checkpoint_data = {}
                storage.create_evolution_job(self.job_id, now)
            self._running = True
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
            return True

    def stop(self):
        with self._lock:
            if not self._running:
                return
            self._stop_flag.set()
        if self._thread:
            self._thread.join(timeout=30)
        with self._lock:
            self._running = False
        if self.job_id:
            storage.update_evolution_job(self.job_id, _now_iso(), status="stopped", stage="stopped")

    def _checkpoint(self, stage, **updates):
        """Same accumulate-then-write-the-whole-dict pattern as
        automation_pipeline.pipeline's checkpoint closure: merge into the
        in-memory dict, then persist the complete, current version -- never
        a partial merge at the storage layer, so a crash right after this
        call always leaves a self-consistent row."""
        self._checkpoint_data.update(updates)
        storage.update_evolution_job(self.job_id, _now_iso(), stage=stage, checkpoint=dict(self._checkpoint_data))

    def _loop(self):
        self._log("[evolution-engine] started")
        while not self._stop_flag.is_set():
            try:
                self._tick()
            except Exception as e:
                self._log(f"[evolution-engine] tick error: {e!r}")
                storage.update_evolution_job(self.job_id, _now_iso(), error=repr(e))
            self._stop_flag.wait(self.tick_interval_seconds)
        with self._lock:
            self._running = False

    def _tick(self):
        """One full Analyze -> Mutate -> Archive -> Rank/Champion pass,
        entirely governed by the Governor: every lineage is enqueued with
        its current score as priority (lowest score = most in need of
        improvement = mutated first), then dequeued only while the
        Governor's per-run experiment budget and real CPU/RAM readings both
        allow it -- so a heavily loaded machine simply does less work this
        tick instead of piling on top of existing load.

        The checkpoint dict is reset at the start of every tick (not
        accumulated across ticks): each tick is a fresh, self-contained
        pass over whatever bot_strategies exist right now, so resuming
        after a crash simply means "run the next fresh tick" rather than
        replaying partial in-tick progress -- the checkpoint's job is to
        make what stage it died in observable, not to skip already-done
        work within a tick."""
        self._checkpoint_data = {}
        self.governor.reset_run_budget()
        self._checkpoint("analyzing")

        for base_id in storage.list_bot_strategy_base_ids():
            latest = storage.latest_generation_for_base(base_id)
            score = latest["evolution_score"] if latest and latest.get("evolution_score") is not None else 50.0
            self.governor.try_enqueue(base_id, priority=score)

        mutated = []
        while self.governor.queue_size() > 0:
            if not self.governor.resource_ok():
                self._log("[evolution-engine] CPU/RAM over limit -- pausing mutation work for this tick")
                break
            if not self.governor.try_start_experiment():
                break
            base_id = self.governor.dequeue()
            if base_id is None:
                break
            new_id = mutator.mutate_strategy(base_id, self.governor, _now_iso())
            if new_id:
                mutated.append(new_id)
        self._checkpoint("mutating", mutated=mutated, queue_remaining=self.governor.queue_size())

        archived = mutator.archive_underperformers(_now_iso())
        self._checkpoint("archiving", archived=archived)

        champions = champion.recompute_champions(_now_iso())
        self._checkpoint("ranking", champions=champions)

        snapshot = {
            "bot_strategy_count": len(storage.list_bot_strategies(status="active", limit=100_000)),
            "bot_lesson_count": len(storage.list_bot_lessons(status="active", limit=100_000)),
            "champions": champions,
            "mutated_this_tick": mutated,
            "archived_this_tick": archived,
        }
        storage.create_knowledge_version("evolution tick", snapshot, _now_iso())
        self._checkpoint("completed", last_tick_at=_now_iso())

    def status(self):
        job = storage.get_evolution_job(self.job_id) if self.job_id else None
        return {"running": self.is_running(), "job": job, "governor": self.governor.stats()}


engine = EvolutionEngine()


def resume_evolution_jobs_on_startup():
    """Same role as automation_pipeline.pipeline.resume_pipeline_jobs_on_startup
    -- called once from sindhu_web/server.py's lifespan. Any evolution_jobs
    row still status='running' means the server stopped mid-tick; pick the
    most recent one back up rather than leaving it stuck forever."""
    running = storage.list_running_evolution_jobs()
    if not running:
        return
    most_recent = max(running, key=lambda j: j["created_at"])
    engine.start(resume_job=most_recent)
