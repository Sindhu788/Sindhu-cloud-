"""Master plan V2 R9 (N3): build docs/SOAK_REPORT.md from D:\\sindhu_runtime\\soak\\soak.csv (soak_monitor.py output)."""
import argparse
import csv
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build(rows):
    n = len(rows)
    if not n:
        return "# SOAK REPORT\n\nNo samples yet.\n"
    up = sum(1 for r in rows if r.get("up") == "1")
    lat = [x for x in (_f(r.get("latency_s")) for r in rows if r.get("up") == "1") if x is not None]
    rss = [x for x in (_f(r.get("rss_mb")) for r in rows) if x is not None]
    starts = []
    for r in rows:
        s = r.get("started_at")
        if s and (not starts or starts[-1] != s):
            starts.append(s)
    commits = sorted({r.get("commit") for r in rows if r.get("commit")})
    scans = [x for x in (_f(r.get("scans_finished")) for r in rows) if x is not None]
    errs = [r for r in rows if r.get("error")]
    down = [r["time_utc"] for r in rows if r.get("up") != "1"]
    lines = ["# SOAK REPORT (master plan V2 R9, N3)", "",
             f"Samples: **{n}** from {rows[0]['time_utc']} to {rows[-1]['time_utc']} (one every ~10 min, public /health and /health/details).",
             "", "| Metric | Value |", "|---|---|",
             f"| Uptime (samples with /health ok) | {100 * up / n:.1f} % ({up} of {n}) |"]
    lines.append(f"| /health latency from the laptop | avg {sum(lat) / len(lat):.2f} s, worst {max(lat):.2f} s |" if lat
                 else "| /health latency | no successful sample |")
    lines.append(f"| Memory (RSS from /health/details) | max {max(rss):.0f} MB, min {min(rss):.0f} MB |" if rss
                 else "| Memory | not exposed in these samples (needs the G1 deploy) |")
    lines.append(f"| Restarts seen (started_at changed) | {max(0, len(starts) - 1)} |")
    lines.append(f"| Commits seen | {', '.join(commits)} |")
    lines.append(f"| Scans finished (counter, per instance) | max {int(max(scans))} |" if scans else "| Scans finished | not exposed |")
    lines.append(f"| Samples with an error | {len(errs)} |")
    if down:
        lines += ["", "Down samples (UTC): " + ", ".join(down[:30]) + (" ..." if len(down) > 30 else "")]
    lines += ["", "Note: the laptop's own internet also counts as 'down' here; one down sample is not proof of a Cloud outage.",
              "A deploy restarts the service, so each deploy shows up as one restart."]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=r"D:\sindhu_runtime\soak\soak.csv")
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "SOAK_REPORT.md"))
    a = ap.parse_args()
    rows = list(csv.DictReader(open(a.csv, encoding="utf-8"))) if os.path.exists(a.csv) else []
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(build(rows))
    print(f"{len(rows)} samples -> {a.out}")


if __name__ == "__main__":
    main()
