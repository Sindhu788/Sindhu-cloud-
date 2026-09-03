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

import random
import threading
import time
from datetime import datetime, timezone

from data_engine import storage, config as base_config
from evolution_engine.governor import Governor
from evolution_engine import mutator, champion
from sindhu_strategy import lifecycle as sindhu_lifecycle

DEFAULT_TICK_INTERVAL_SECONDS = 300  # one evolution tick every 5 minutes
# Batch 3, Task 4: the real gap that kept the loop idle -- the daily
# generator (and this engine's own mutation step) both create new BOT
# strategy generations, but nothing ever gave any of them a first real
# backtest, so none could ever accumulate the trades needed to reach
# Batch 1's 100-trade evolution gate. Deliberately modest and separate
# from the mutation experiment budget below: a full-scale (50-coin) real
# backtest is real CPU work, and this is meant to be a slow, continuous,
# low-priority background drain of the candidate backlog on an 8GB
# machine, not a burst. At 1 candidate/tick and a ~5-minute tick period,
# the current ~230-candidate backlog drains in a few days, not competing
# with real user-strategy backtests for resources.
UNTESTED_CANDIDATES_PER_TICK = 1
UNTESTED_BACKTEST_COIN_COUNT = 10  # a lighter real sample than the full 50-coin treatment user strategies get
# +/-15% jitter on every wait between ticks, so a fixed 300s period never
# stays permanently aligned with Paper Trading's own tick interval (also a
# fixed period, configured separately in paper_trading/config.py) or the
# SINDHU Strategy scheduler's hourly check -- two independently-fixed
# periods that happen to start at the same moment stay aligned forever
# without jitter, repeatedly colliding on the same DB-write window every
# time they coincide. This alone doesn't fix write contention (the _DB_LOCK
# in data_engine.storage.get_conn() does that), it just reduces how often
# collisions are even attempted.
TICK_JITTER_FRACTION = 0.15


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

    def _checkpoint(self, stage, clear_error=False, **updates):
        """Same accumulate-then-write-the-whole-dict pattern as
        automation_pipeline.pipeline's checkpoint closure: merge into the
        in-memory dict, then persist the complete, current version -- never
        a partial merge at the storage layer, so a crash right after this
        call always leaves a self-consistent row. clear_error=True (passed
        by the final "completed" checkpoint) blanks out a previous tick's
        error message -- without this, one transient failure's message
        (e.g. a "database is locked" collision, now far rarer after the
        _DB_LOCK fix in storage.get_conn() but never impossible to hit
        zero times) stayed displayed on the dashboard forever, even hours
        after ticks resumed succeeding normally."""
        self._checkpoint_data.update(updates)
        storage.update_evolution_job(
            self.job_id, _now_iso(), stage=stage, checkpoint=dict(self._checkpoint_data),
            error="" if clear_error else None,
        )

    def _loop(self):
        self._log("[evolution-engine] started")
        while not self._stop_flag.is_set():
            try:
                self._tick()
            except Exception as e:
                self._log(f"[evolution-engine] tick error: {e!r}")
                storage.update_evolution_job(self.job_id, _now_iso(), error=repr(e))
            # Jittered wait (see TICK_JITTER_FRACTION) so this loop's period
            # doesn't stay permanently lock-stepped with another background
            # system's own fixed interval.
            jitter = self.tick_interval_seconds * TICK_JITTER_FRACTION
            wait_seconds = self.tick_interval_seconds + random.uniform(-jitter, jitter)
            self._stop_flag.wait(wait_seconds)
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
        work within a tick.

        Resources are checked FIRST, before any DB work at all -- not just
        inside the mutation loop below. Diagnosed live: a heavily-loaded
        box (real cpu_percent measured at 100.0) still paid for the
        analyzing/archiving/ranking DB reads and writes every 5 minutes
        even though the mutation loop itself correctly refused to do
        anything, because resource_ok() was only ever consulted from
        inside that loop. A fully loaded system now skips the entire tick."""
        self._checkpoint_data = {}
        self.governor.reset_run_budget()

        if not self.governor.resource_ok():
            gov_stats = self.governor.stats()
            self._log(f"[evolution-engine] CPU/RAM over limit "
                      f"(cpu={gov_stats['cpu_percent']}%, ram={gov_stats['ram_percent']}%) -- skipping this tick entirely")
            self._checkpoint("skipped_over_resource_limit", clear_error=True)
            return

        self._checkpoint("analyzing")

        tested = self._backtest_untested_candidates(_now_iso())
        self._checkpoint("backtesting_candidates", tested=tested)

        # Cleared before re-deriving the candidate list fresh: a tick that
        # errors out partway through the mutation loop below otherwise
        # leaves stale, already-considered items sitting in the queue
        # forever (see governor.clear_queue()'s docstring for the exact
        # 16-hour-stuck-at-max symptom this caused).
        self.governor.clear_queue()
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
            # Grand Feature Expansion, Phase 6 Feature 9: Regime-Aware
            # Evolution -- mutate_strategy's own regime-adaptation branch
            # was previously dead code here (this call never passed
            # exchange/symbol/timeframe). regime_context_for() derives all
            # 3 from the lineage's own last real backtest.
            reg_exchange, reg_symbol, reg_timeframe = mutator.regime_context_for(base_id)
            new_id = mutator.mutate_strategy(base_id, self.governor, _now_iso(),
                                              exchange=reg_exchange, symbol=reg_symbol, timeframe=reg_timeframe)
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
        self._checkpoint("completed", last_tick_at=_now_iso(), clear_error=True)

    def _backtest_untested_candidates(self, now_iso):
        """(Batch 3, Task 4) Feeds newly-generated BOT candidates into the
        real backtest pipeline -- see the module-level comment on
        UNTESTED_CANDIDATES_PER_TICK for why this exists and why it's
        deliberately small. Uses the SAME Governor resource check as the
        mutation loop (never runs a real backtest on an already-loaded
        machine) but its own, separate, always-available budget (not
        governor.try_start_experiment()'s per-tick experiment counter,
        which the mutation loop below still governs on its own) -- a
        first backtest and a mutation are different kinds of work and
        competing for the same tiny per-tick counter would starve
        whichever runs second. Never touches the 100-trade evolution gate
        or the rollback mechanism (evolution_engine.rollback) -- this
        only ever produces the trade data those already-built mechanisms
        read; it doesn't decide anything about mutation eligibility
        itself. Returns a list of {"id", "validated", "trades"} for
        whatever ran this tick (empty if resources were tight or nothing
        was untested)."""
        if not self.governor.resource_ok():
            return []
        exchange_cfg = base_config.load_or_seed("exchanges.json", base_config.DEFAULTS["exchanges.json"])
        exchange = exchange_cfg["default"]
        symbols = storage.load_symbols(exchange)[:UNTESTED_BACKTEST_COIN_COUNT]
        if not symbols:
            self._log("[evolution-engine] no downloaded coins available yet -- skipping candidate backtests this tick")
            return []

        tested = []
        for row in storage.list_untested_bot_strategies(limit=UNTESTED_CANDIDATES_PER_TICK):
            if not self.governor.resource_ok():
                break
            try:
                result = sindhu_lifecycle.validate_and_backtest(row["id"], exchange, symbols, use_multiprocessing=False)
                trades = (result.get("backtest_summary") or {}).get("trades")
                tested.append({"id": row["id"], "validated": result["validated"], "trades": trades})
                self._log(f"[evolution-engine] first backtest done for {row['id']} ({row['name']}): "
                          f"{'valid, ' + str(trades) + ' trades' if result['validated'] else 'invalid config'}")
            except Exception as e:
                self._log(f"[evolution-engine] first backtest failed for {row['id']}: {e!r}")
        return tested

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
