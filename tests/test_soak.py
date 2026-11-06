"""Master plan V2 R9 (N3): soak monitor rows and report."""
import csv
import importlib.util
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "ops", "soak", name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


soak_monitor = _load("soak_monitor")
soak_report = _load("soak_report")


def test_sample_handles_a_down_service(monkeypatch):
    import requests

    def boom(*a, **k):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(soak_monitor.requests, "get", boom)
    row = soak_monitor.sample("http://x")
    assert row["up"] == 0 and row["error"] == "ConnectionError"


def test_report_counts_uptime_restarts_and_memory(tmp_path):
    p = tmp_path / "s.csv"
    for i in range(5):
        r = dict(time_utc=f"2026-11-06T0{i}:00:00Z", up="1" if i != 2 else "0", latency_s="0.7", commit="abc",
                 started_at="A" if i < 3 else "B", rss_mb=str(380 + i), scans_finished=str(i))
        soak_monitor.append(str(p), {k: r.get(k, "") for k in soak_monitor.COLUMNS})
    got = list(csv.DictReader(open(p, encoding="utf-8")))
    text = soak_report.build(got)
    assert "80.0 %" in text and "| Restarts seen (started_at changed) | 1 |" in text and "max 384 MB" in text


def test_health_details_has_memory_and_scans():
    from paper_trading import self_check
    d = self_check.details()
    assert "memory" in d and "scans_finished" in d
