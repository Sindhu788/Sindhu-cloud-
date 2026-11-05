"""Memory release helpers for the 512 MB free plan (Day 8). They never change what the program computes; they only hand freed memory back.

Why: on Render (Linux, glibc) every thread that allocates gets its own malloc "arena", and glibc rarely returns freed pages to the operating system.
The scan uses several threads (4 prefetch workers, the engine thread, the housekeeper thread, database helpers), so after pandas/numpy temporary frames are
freed the process keeps the pages. That makes peak memory depend on thread timing: the same code measured 389 to 459 MB on different Cloud instances
(docs/SCAN_PROFILE.md section 13). Two standard remedies, both safe:
 - cap_arenas(): at process start tell glibc to use at most 2 arenas (the in-process equivalent of the environment variable MALLOC_ARENA_MAX=2).
 - release_memory(): after each coin run the garbage collector and call malloc_trim(0), which returns free heap pages to the system.
Both are no-ops outside Linux (the laptop runs Windows: only the garbage collection runs there) and can be switched off with SINDHU_MEMORY_TRIM=0.
The effect on Cloud is measured in docs/SCAN_PROFILE.md section 15; it could not be tested locally (no Linux here), so it is verified only on Cloud.
"""
import ctypes
import gc
import os
import sys
import threading
import time

M_ARENA_MAX = -8
_stats = {"calls": 0, "seconds": 0.0, "trimmed": 0, "collected": 0}
_lock = threading.Lock()
_libc_cache = []


def enabled():
    return str(os.environ.get("SINDHU_MEMORY_TRIM", "1")).strip().lower() not in ("0", "false", "no", "off")


def _libc():
    if not sys.platform.startswith("linux"):
        return None
    if not _libc_cache:
        try:
            _libc_cache.append(ctypes.CDLL("libc.so.6"))
        except OSError:
            _libc_cache.append(None)
    return _libc_cache[0]


def cap_arenas(n=2, libc=None):
    """Limit glibc malloc arenas to `n`. Call once, as early as possible (before worker threads exist). Returns True when it took effect."""
    try:
        if not enabled() or os.environ.get("MALLOC_ARENA_MAX"):
            return False
        lib = libc if libc is not None else _libc()
        return bool(lib is not None and lib.mallopt(M_ARENA_MAX, int(n)) == 1)
    except Exception:
        return False


def release_memory(libc=None):
    """Garbage-collect and, on Linux, give free heap pages back to the system. Never raises; returns a small dict for logging."""
    if not enabled():
        return {"skipped": True}
    t0 = time.perf_counter()
    trimmed = False
    collected = 0
    try:
        collected = gc.collect()
        lib = libc if libc is not None else _libc()
        if lib is not None:
            trimmed = bool(lib.malloc_trim(0))
    except Exception:
        pass
    dt = time.perf_counter() - t0
    with _lock:
        _stats["calls"] += 1
        _stats["seconds"] += dt
        _stats["trimmed"] += int(trimmed)
        _stats["collected"] += int(collected)
    return {"seconds": dt, "trimmed": trimmed, "collected": collected}


def stats():
    with _lock:
        return dict(_stats)
