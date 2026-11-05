"""Master plan A4 (P27 + S1): per-exchange request pacing for public market-data calls.

- Token bucket per exchange: at most `rate` requests per second on average, bursts up to `burst`. Defaults are well under the
  documented public limits (OKX market candles 40 requests / 2 s per IP, history-candles 20 / 2 s): okx 8/s, others 10/s.
  Override: SINDHU_RATE_<EXCHANGE>=<per second>, e.g. SINDHU_RATE_OKX=5.
- At most SINDHU_MAX_PARALLEL_PER_EXCHANGE (default 3) requests in flight per exchange.
- After an HTTP 429 / OKX 50011 "Too Many Requests", the rate is halved for 10 minutes (then back to normal).
Thread-safe, never raises, and adds no wait at all while the bucket has tokens.
"""
import os
import threading
import time

_DEFAULT_RATE = {"okx": 8.0}
_FALLBACK_RATE = 10.0
_COOLDOWN_S = 600.0

_lock = threading.Lock()
_buckets = {}


def _env_float(name, default):
    try:
        v = float(os.environ.get(name, default))
        return v if v > 0 else default
    except ValueError:
        return default


class Bucket:
    def __init__(self, exchange_id, rate=None, burst=None, parallel=None, clock=time.monotonic, sleep=time.sleep):
        self.id = exchange_id
        self.base_rate = rate or _env_float(f"SINDHU_RATE_{exchange_id.upper()}", _DEFAULT_RATE.get(exchange_id, _FALLBACK_RATE))
        self.burst = burst or max(1.0, self.base_rate)
        self.tokens = self.burst
        self.clock, self.sleep = clock, sleep
        self.last = clock()
        self.slow_until = 0.0
        self.lock = threading.Lock()
        n = parallel or int(_env_float("SINDHU_MAX_PARALLEL_PER_EXCHANGE", 3))
        self.parallel = threading.BoundedSemaphore(max(1, n))
        self.waited_s = 0.0
        self.limited_events = 0

    def rate(self):
        return self.base_rate / 2 if self.clock() < self.slow_until else self.base_rate

    def take(self):
        """Block until one request may start (returns the seconds waited)."""
        waited = 0.0
        while True:
            with self.lock:
                now = self.clock()
                self.tokens = min(self.burst, self.tokens + (now - self.last) * self.rate())
                self.last = now
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    self.waited_s += waited
                    return waited
                need = (1.0 - self.tokens) / self.rate()
            self.sleep(need)
            waited += need

    def rate_limited(self):
        """Called after a 429 / 50011: halve the rate for 10 minutes and drop the burst allowance."""
        with self.lock:
            self.slow_until = self.clock() + _COOLDOWN_S
            self.tokens = 0.0
            self.limited_events += 1

    def stats(self):
        with self.lock:
            return {"rate_per_s": self.rate(), "slowed": self.clock() < self.slow_until, "waited_s": round(self.waited_s, 1),
                    "rate_limited_events": self.limited_events}


def bucket(exchange_id):
    with _lock:
        b = _buckets.get(exchange_id)
        if b is None:
            b = _buckets[exchange_id] = Bucket(exchange_id)
        return b


def reset():
    with _lock:
        _buckets.clear()
