"""A.3 -- Evolution Governor. The one place that decides whether the
Evolution Engine (or the SINDHU Strategy Generator's backtest routing) is
allowed to do more work right now. Every limit here is a concrete number
enforced in code, not a documented convention: max experiments per run, max
generations per strategy, a hard-capped experiment queue, and a real
CPU/RAM check via psutil (already a dependency -- see sindhu_web/api/home.py)
before anything CPU-heavy is allowed to start.
"""

import heapq
import itertools
import threading
import time

import psutil

# ---- concrete limits (A.3: "enforce concrete limits, not just theoretical ones") ----
# CPU/RAM limits were originally sized as if Evolution were the only
# background consumer on the box. With Paper Trading (per active strategy),
# the SINDHU Strategy daily scheduler, and the automation pipeline all now
# also running continuously, 75%/85% left no headroom for the OTHER
# systems' own usage plus the dashboard's own request-serving threads --
# diagnosed live: real cpu_percent read 100.0 while only Evolution was
# doing background work, well past the old 75% ceiling, yet resource_ok()
# was only ever consulted from inside the mutation loop (see engine.py's
# _tick(), fixed alongside this), so checkpoint writes and the Champion
# Engine's own DB reads/writes still ran every tick regardless. Tightened
# here to leave real combined headroom across ALL background systems, not
# just Evolution's own share.
MAX_EXPERIMENTS_PER_RUN = 5      # how many mutation/backtest experiments one engine tick may launch
MAX_GENERATIONS_PER_STRATEGY = 25  # generation_manager.create_next_strategy_generation stops here
MAX_QUEUE_SIZE = 20              # research/experiment queue never grows past this many pending items
CPU_LIMIT_PERCENT = 60.0         # refuse new work above this instantaneous CPU load (was 75.0)
RAM_LIMIT_PERCENT = 80.0         # refuse new work above this RAM usage (was 85.0)
BACKOFF_SECONDS = 5.0            # how long to wait before re-checking resources when over limit


class QueueFullError(Exception):
    pass


class Governor:
    """Not a singleton by force -- the Evolution Engine background loop
    owns exactly one instance, created once in engine.py, so state (queue,
    experiment counter) is naturally per-process. Thread-safe: engine.py's
    loop and the FastAPI request thread (status endpoint) may both touch
    this at once."""

    def __init__(self, max_experiments_per_run=MAX_EXPERIMENTS_PER_RUN,
                 max_generations_per_strategy=MAX_GENERATIONS_PER_STRATEGY,
                 max_queue_size=MAX_QUEUE_SIZE,
                 cpu_limit=CPU_LIMIT_PERCENT, ram_limit=RAM_LIMIT_PERCENT):
        self.max_experiments_per_run = max_experiments_per_run
        self.max_generations_per_strategy = max_generations_per_strategy
        self.max_queue_size = max_queue_size
        self.cpu_limit = cpu_limit
        self.ram_limit = ram_limit
        self._lock = threading.Lock()
        self._queue = []  # heap of (priority, seq, item)
        self._seq = itertools.count()
        self._experiments_this_run = 0
        self._last_resource_check = {"cpu_percent": 0.0, "ram_percent": 0.0, "checked_at": None}

    # ---- resource protection ----
    def check_resources(self):
        """Real psutil reading, not a cached/mocked value -- this is what
        the load test (Phase 7A verification #4) exercises directly. cpu_
        percent(interval=0.1) blocks for 100ms to get a real instantaneous
        sample rather than the meaningless "0.0 on first call ever" psutil
        gives with interval=None."""
        cpu = psutil.cpu_percent(interval=0.1)
        ram = psutil.virtual_memory().percent
        self._last_resource_check = {"cpu_percent": cpu, "ram_percent": ram, "checked_at": time.time()}
        return cpu, ram

    def resource_ok(self):
        cpu, ram = self.check_resources()
        return cpu < self.cpu_limit and ram < self.ram_limit

    def wait_for_resources(self, max_wait_seconds=60):
        """Blocks (in the caller's own background thread -- never the web
        server's request thread) until resources are under the limit or
        max_wait_seconds elapses. Returns True if it's now safe to proceed,
        False if it gave up waiting -- caller should skip this tick rather
        than force the work through."""
        waited = 0.0
        while not self.resource_ok():
            if waited >= max_wait_seconds:
                return False
            time.sleep(BACKOFF_SECONDS)
            waited += BACKOFF_SECONDS
        return True

    # ---- experiment budget (per engine run/tick) ----
    def reset_run_budget(self):
        with self._lock:
            self._experiments_this_run = 0

    def try_start_experiment(self):
        """Returns True iff this call is allowed to launch one more
        experiment this run -- the hard cap on A.2's "Analyze, Compare,
        Improve, Mutate..." work per tick."""
        with self._lock:
            if self._experiments_this_run >= self.max_experiments_per_run:
                return False
            self._experiments_this_run += 1
            return True

    # ---- bounded, priority-ordered research/experiment queue ----
    def enqueue(self, item, priority=5):
        """Lower `priority` number = runs sooner (matches paper_trading's
        existing priority_rule convention: confidence/win_rate/profit all
        sort descending, so callers should pass e.g. `-score` for
        "highest score first"). Raises QueueFullError instead of growing
        unbounded -- the queue itself is a concrete resource limit."""
        with self._lock:
            if len(self._queue) >= self.max_queue_size:
                raise QueueFullError(f"experiment queue full ({self.max_queue_size} items)")
            heapq.heappush(self._queue, (priority, next(self._seq), item))

    def try_enqueue(self, item, priority=5):
        try:
            self.enqueue(item, priority)
            return True
        except QueueFullError:
            return False

    def dequeue(self):
        with self._lock:
            if not self._queue:
                return None
            return heapq.heappop(self._queue)[2]

    def queue_size(self):
        with self._lock:
            return len(self._queue)

    def clear_queue(self):
        """Drops every pending item. Each Evolution Engine tick re-derives
        the full candidate list fresh from storage (see engine.py's
        _tick()), so leftover items from a tick that errored out partway
        through are stale by the next tick -- without this, a tick that
        fails after dequeuing N items (but before finishing) leaves the
        queue permanently short by N forever, since the next tick's blind
        re-enqueue-everything only tops it back up to whatever headroom is
        left, never truly resetting it. Diagnosed live: queue_size sat at
        its max (20/20) for 16+ hours straight because of exactly this."""
        with self._lock:
            self._queue.clear()

    # ---- reporting (backs the Evolution Dashboard) ----
    def stats(self):
        with self._lock:
            return {
                "cpu_percent": self._last_resource_check["cpu_percent"],
                "ram_percent": self._last_resource_check["ram_percent"],
                "resource_checked_at": self._last_resource_check["checked_at"],
                "cpu_limit_percent": self.cpu_limit,
                "ram_limit_percent": self.ram_limit,
                "queue_size": len(self._queue),
                "max_queue_size": self.max_queue_size,
                "experiments_this_run": self._experiments_this_run,
                "max_experiments_per_run": self.max_experiments_per_run,
                "max_generations_per_strategy": self.max_generations_per_strategy,
            }
