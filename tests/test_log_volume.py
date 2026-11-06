"""Master plan V2 R6 (P29): fewer repetitive log lines, nothing lost that matters (errors, non-GET, 4xx/5xx), lines counted per hour."""
import io
import logging

from paper_trading import log_volume, memory_guard


def _rec(name, level, msg, args=()):
    return logging.LogRecord(name, level, __file__, 1, msg, args, None)


def test_access_filter_drops_only_successful_get_and_head():
    f = log_volume._AccessFilter()
    fmt = '%s - "%s %s HTTP/%s" %d'
    assert not f.filter(_rec("uvicorn.access", logging.INFO, fmt, ("1.2.3.4:0", "GET", "/api/home", "1.1", 200)))
    assert not f.filter(_rec("uvicorn.access", logging.INFO, fmt, ("1.2.3.4:0", "HEAD", "/health", "1.1", 200)))
    assert f.filter(_rec("uvicorn.access", logging.INFO, fmt, ("1.2.3.4:0", "POST", "/api/auth/login", "1.1", 401)))
    assert f.filter(_rec("uvicorn.access", logging.INFO, fmt, ("1.2.3.4:0", "POST", "/api/settings", "1.1", 200)))
    assert f.filter(_rec("uvicorn.access", logging.INFO, fmt, ("1.2.3.4:0", "GET", "/api/x", "1.1", 500)))
    assert f.filter(_rec("uvicorn.access", logging.INFO, fmt, ("1.2.3.4:0", "GET", "/nope", "1.1", 404)))


def test_websocket_noise_filter_keeps_errors():
    f = log_volume._WebsocketNoiseFilter()
    assert not f.filter(_rec("uvicorn.error", logging.INFO, "connection open"))
    assert not f.filter(_rec("uvicorn.error", logging.INFO, '1.2.3.4:0 - "WebSocket /ws/logs" [accepted]'))
    assert f.filter(_rec("uvicorn.error", logging.ERROR, "connection open"))
    assert f.filter(_rec("uvicorn.error", logging.INFO, "Application startup complete."))


def test_counting_stream_counts_lines():
    log_volume._buckets.clear()
    s = log_volume._CountingStream(io.StringIO())
    s.write("a\nb\n"); s.write("c"); s.write("\n")
    assert log_volume.stats()["this_hour"] == 3


def test_memory_guard_prints_once_per_level_change_then_every_30_min(monkeypatch):
    lines = []
    memory_guard._log_state.update(level="ok", at=-1e9, skipped=0)
    clock = [1000.0]
    monkeypatch.setattr(memory_guard.time, "monotonic", lambda: clock[0])
    for i in range(10):                          # 10 checks a minute apart at soft level
        memory_guard.check(log=lines.append, rss=memory_guard.SOFT_MB + 5)
        clock[0] += 60
    assert len(lines) == 1
    clock[0] += 1800
    memory_guard.check(log=lines.append, rss=memory_guard.SOFT_MB + 5)
    assert len(lines) == 2 and "repeats not printed" in lines[1]
    memory_guard.check(log=lines.append, rss=memory_guard.HARD_MB + 5)   # level change: printed at once
    assert len(lines) == 3
    memory_guard.check(log=lines.append, rss=10)


def test_health_details_has_log_lines():
    from paper_trading import self_check
    assert "log_lines" in self_check.details()
