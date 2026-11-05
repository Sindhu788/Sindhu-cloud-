"""Cheap per-stage wall-clock timer for the scan (Day 8). Pure in-memory counters: no database writes, no network, no files. It exists so that the next Cloud
scans show where the time goes (docs/SCAN_PROFILE.md section 15). Every method is safe to call from any thread and never raises, so it cannot break a scan.
Cost: two perf_counter() calls and one dictionary update per stage (about 1-3 microseconds)."""
import threading
import time
from contextlib import contextmanager


class StageTimer:
    def __init__(self):
        self._lock = threading.Lock()
        self.seconds = {}
        self.counts = {}

    def add(self, name, seconds):
        try:
            with self._lock:
                self.seconds[name] = self.seconds.get(name, 0.0) + seconds
                self.counts[name] = self.counts.get(name, 0) + 1
        except Exception:
            pass

    @contextmanager
    def stage(self, name):
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.add(name, time.perf_counter() - t0)

    def snapshot(self):
        with self._lock:
            return dict(self.seconds), dict(self.counts)

    def summary(self, order=None):
        try:
            sec, cnt = self.snapshot()
            names = [n for n in (order or []) if n in sec] + sorted(n for n in sec if n not in (order or []))
            return " | ".join(f"{n} {sec[n]:.1f}s x{cnt[n]}" for n in names)
        except Exception:
            return ""

    def delta_since(self, before):
        """Seconds per stage since a previous snapshot()[0] (used for the per-coin line)."""
        try:
            now, _ = self.snapshot()
            return {n: now[n] - before.get(n, 0.0) for n in now if now[n] - before.get(n, 0.0) > 0.0005}
        except Exception:
            return {}
