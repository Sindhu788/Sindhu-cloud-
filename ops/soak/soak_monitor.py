"""Master plan V2 R9 (N3): 48-hour soak monitor for the Cloud service. Public endpoints only (/health, /health/details); no secrets.

Every --every seconds (default 600) it appends one row to D:\\sindhu_runtime\\soak\\soak.csv:
time_utc, up, http_status, latency_s, commit, started_at, rss_mb, memory_level, scans_finished, stale_series, fresh_series,
config_errors, db_breaker_open, log_lines_last_hour, error.
Runs for --hours (default 48) then stops. Safe to run twice: rows are only appended. Usage (stable venv):
    python ops/soak/soak_monitor.py [--hours 48] [--every 600] [--base https://sindhu-cloud-1.onrender.com]"""
import argparse
import csv
import os
import time
from datetime import datetime, timezone

import requests

COLUMNS = ["time_utc", "up", "http_status", "latency_s", "commit", "started_at", "rss_mb", "memory_level", "scans_finished",
           "stale_series", "fresh_series", "config_errors", "db_breaker_open", "log_lines_last_hour", "error"]
DEFAULT_OUT = r"D:\sindhu_runtime\soak\soak.csv"


def sample(base, timeout=60):
    row = {k: "" for k in COLUMNS}
    row["time_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    t0 = time.monotonic()
    try:
        r = requests.get(base + "/health", timeout=timeout)
        row["latency_s"] = round(time.monotonic() - t0, 3)
        row["http_status"] = r.status_code
        h = r.json() if r.ok else {}
        row["up"] = int(r.ok and h.get("status") == "ok")
        row["commit"] = h.get("commit", "")
        row["started_at"] = h.get("started_at", "")
    except Exception as e:
        row["up"] = 0
        row["latency_s"] = round(time.monotonic() - t0, 3)
        row["error"] = type(e).__name__
        return row
    try:
        d = requests.get(base + "/health/details", timeout=timeout).json()
        mem = d.get("memory") or {}
        cand = d.get("candles") or {}
        row.update(rss_mb=mem.get("rss_mb", ""), memory_level=mem.get("level", ""), scans_finished=d.get("scans_finished", ""),
                   stale_series=cand.get("stale", ""), fresh_series=cand.get("fresh", ""),
                   config_errors=len(d.get("config_errors") or {}),
                   db_breaker_open=int(bool((d.get("db_breaker") or {}).get("open"))),
                   log_lines_last_hour=(d.get("log_lines") or {}).get("last_full_hour", ""))
    except Exception as e:
        row["error"] = "details:" + type(e).__name__
    return row


def append(path, row):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if new:
            w.writeheader()
        w.writerow(row)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://sindhu-cloud-1.onrender.com")
    ap.add_argument("--hours", type=float, default=48)
    ap.add_argument("--every", type=float, default=600)
    ap.add_argument("--out", default=DEFAULT_OUT)
    a = ap.parse_args()
    end = time.monotonic() + a.hours * 3600
    while True:
        row = sample(a.base.rstrip("/"))
        append(a.out, row)
        print(row["time_utc"], "up" if row["up"] else "DOWN", row["latency_s"], row["rss_mb"], row["error"], flush=True)
        if time.monotonic() + a.every > end:
            break
        time.sleep(a.every)


if __name__ == "__main__":
    main()
