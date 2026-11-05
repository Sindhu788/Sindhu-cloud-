"""Forward-test report (Day 7 Step 15) for the pre-registered test in docs/BACKTEST_PROTOCOL.md section 9.

Reads paper trades from a Cloud export folder (JSON lines, made by scripts/backup_cloud_export.py; read-only, no Cloud schema change) and counts ONLY positions
that were OPENED on or after the forward window start (default 2026-11-06 00:00 UTC) and are closed. Before the earliest evaluation date (default 2027-01-05) it prints
COUNTS AND DATA-QUALITY NOTES ONLY: no profit, no win rate, no profit factor, no verdict. Even after that date a verdict is computed only for strategies that were
registered in `manifest/forward_registry.json` BEFORE the window, and every verdict is written to the append-only file `manifest/forward_looks.log`.
There is deliberately no command-line option to change the date or to force a verdict: the clock of the computer decides.
Usage: python tools/forward_report.py [--export <folder>] [--registry <file>] [--out <folder>]"""
import argparse
import collections
import datetime as dt
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEFAULT_REGISTRY = r"D:\sindhu_data\manifest\forward_registry.json"
DEFAULT_EXPORTS = r"D:\sindhu_backup_phase0"
DEFAULT_OUT = r"D:\sindhu_data\forward_reports"
LOOKS_LOG = r"D:\sindhu_data\manifest\forward_looks.log"


class ForwardTestTooEarly(Exception):
    """Raised by evaluate() when a verdict is requested before the pre-registered evaluation date."""


def _ms(iso):
    return int(dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)


def load_jsonl(folder, table):
    p = os.path.join(folder, table + ".jsonl")
    return [json.loads(l) for l in open(p, encoding="utf-8")] if os.path.exists(p) else []


def load_registry(path):
    r = json.load(open(path, encoding="utf-8"))
    r["_start_ms"] = _ms(r["forward_window_start_utc"])
    r["_earliest"] = dt.date.fromisoformat(r["earliest_evaluation_date"])
    return r


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def select(positions, start_ms):
    """Forward positions = opened on or after the window start AND closed. Also returns how many were closed in the window but opened before (excluded)."""
    fwd, open_fwd, excluded_old = [], [], 0
    for p in positions:
        opened = f(p.get("entry_time"))
        if opened is None:
            continue
        if opened >= start_ms:
            (fwd if p.get("status") == "closed" else open_fwd).append(p)
        elif p.get("status") == "closed" and (f(p.get("exit_time")) or 0) >= start_ms:
            excluded_old += 1
    return fwd, open_fwd, excluded_old


def quality_notes(positions, fwd, open_fwd, scans, start_ms, today):
    notes = []
    ids = collections.Counter(p.get("id") for p in positions)
    dup = sum(1 for v in ids.values() if v > 1)
    notes.append(f"duplicate position ids in the export: {dup}")
    bad = sum(1 for p in fwd if f(p.get("pnl")) is None or not f(p.get("risk_amount")))
    notes.append(f"closed forward positions missing pnl or risk amount: {bad} of {len(fwd)}")
    stale = [p for p in open_fwd if (today_ms(today) - f(p["entry_time"])) > 7 * 86_400_000]
    notes.append(f"forward positions still open after more than 7 days: {len(stale)} of {len(open_fwd)}")
    done = sorted(_ms(s["completed_at"]) for s in scans if s.get("completed_at") and s.get("outcome") == "complete" and _ms(s["completed_at"]) >= start_ms)
    days = max(0, (today - dt.datetime.fromtimestamp(start_ms / 1000, dt.timezone.utc).date()).days + 1) if today >= dt.datetime.fromtimestamp(start_ms / 1000, dt.timezone.utc).date() else 0
    if days:
        per_day = collections.Counter(dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).date() for t in done)
        gap = max(((b - a) / 3_600_000 for a, b in zip(done, done[1:])), default=0.0)
        notes.append(f"days since the window start: {days}; days with at least one completed scan record: {len(per_day)}; longest gap between completed scans: {gap:.1f} h")
        notes.append("(the free Cloud instance sleeps without a pinger: gaps mean missed signals, not missing data)")
    else:
        notes.append("the forward window has not started yet: no scan coverage to report")
    return notes


def today_ms(today):
    return int(dt.datetime(today.year, today.month, today.day, tzinfo=dt.timezone.utc).timestamp() * 1000) + 86_399_999


def counts_by_strategy(fwd, open_fwd):
    c = collections.defaultdict(lambda: {"name": "", "closed": 0, "open": 0})
    for p in fwd:
        d = c[p.get("strategy_id")]; d["name"] = p.get("strategy_name") or d["name"]; d["closed"] += 1
    for p in open_fwd:
        d = c[p.get("strategy_id")]; d["name"] = p.get("strategy_name") or d["name"]; d["open"] += 1
    return c


def evaluate(strategy_positions, registry, today):
    """Pre-registered verdict for ONE registered strategy. Refuses before the evaluation date. Only criteria computable from paper trades are computed; the
    rest are marked NOT COMPUTED (they need the forward candles)."""
    if today < registry["_earliest"]:
        raise ForwardTestTooEarly(f"no verdict before {registry['_earliest']} (today is {today})")
    from data_platform import metrics, rigor
    n = len(strategy_positions)
    out = {"positions": n, "min_positions": registry.get("min_positions", 100), "criteria": []}
    if n < out["min_positions"]:
        out["verdict"] = "INSUFFICIENT_DATA"
        out["criteria"].append(("positions >= minimum", f"{n} of {out['min_positions']}", "FAIL"))
        return out
    pnl = [f(p["pnl"]) for p in strategy_positions]
    pf = metrics.profit_factor(pnl)
    boot = rigor.cluster_bootstrap(pnl, [int(f(p["exit_time"]) // 86_400_000) for p in strategy_positions], n_boot=1000, seed=11)
    out["criteria"] += [("positions >= minimum", f"{n}", "PASS"),
                        ("profit factor >= 1.2 at paper costs (x1)", f"{pf:.2f}", "PASS" if pf >= 1.2 else "FAIL"),
                        ("profit factor > 1.0 at costs x1.5", "paper costs are fixed; needs a re-pricing from candles", "NOT COMPUTED"),
                        ("lower end of the 95 % PF interval > 1", f"{boot['pf_ci'][0]:.2f}", "PASS" if boot["pf_ci"][0] > 1 else "FAIL"),
                        ("random-entry null model p < 0.05", "needs the forward candles", "NOT COMPUTED"),
                        ("beats the best baseline", "needs the forward candles", "NOT COMPUTED")]
    fails = [c for c in out["criteria"] if c[2] == "FAIL"]
    out["verdict"] = "FAILED" if fails else ("CANNOT CONCLUDE (criteria not computed)" if any(c[2] == "NOT COMPUTED" for c in out["criteria"]) else "PASSED")
    return out


def build_report(positions, scans, registry, today):
    start_ms = registry["_start_ms"]
    fwd, open_fwd, excluded_old = select(positions, start_ms)
    counts = counts_by_strategy(fwd, open_fwd)
    registered = {c["strategy_id"] for c in registry.get("candidates", []) if isinstance(c, dict) and "strategy_id" in c}
    L = [f"# Forward-test report - generated {today} (UTC date of the computer)", "",
         f"Window: positions OPENED on or after {registry['forward_window_start_utc']} and closed. Earliest evaluation date: **{registry['_earliest']}**; minimum {registry.get('min_positions', 100)} closed positions per registered candidate.",
         f"Registered candidates: {len(registered)}", ""]
    early = today < registry["_earliest"]
    if early:
        L += [f"**NO VERDICT: the pre-registered evaluation date is {registry['_earliest']} ({(registry['_earliest'] - today).days} days away). Only counts and data-quality notes are shown; profit, win rate and profit factor are deliberately not printed.**", ""]
    L += [f"Forward positions closed: **{len(fwd)}**; still open: **{len(open_fwd)}**; closed in the window but opened before it (excluded): {excluded_old}", "",
          "| Strategy | Closed | Open | Registered | Closed toward the minimum |", "|---|---|---|---|---|"]
    for sid, c in sorted(counts.items(), key=lambda kv: -kv[1]["closed"]):
        L.append(f"| {c['name'] or sid} | {c['closed']} | {c['open']} | {'yes' if sid in registered else 'no'} | {c['closed']} / {registry.get('min_positions', 100)} |")
    if not counts:
        L.append("| (none yet) | 0 | 0 | - | - |")
    L += ["", "## Data-quality notes"] + [f"- {n}" for n in quality_notes(positions, fwd, open_fwd, scans, start_ms, today)]
    if not early:
        L += ["", "## Verdicts (registered candidates only)"]
        by = collections.defaultdict(list)
        for p in fwd:
            by[p.get("strategy_id")].append(p)
        if not registered:
            L.append("- no candidate was registered before the window: no verdict is possible for any strategy.")
        own = {c["strategy_id"]: max(start_ms, _ms(c["window_start_utc"])) if c.get("window_start_utc") else start_ms for c in registry.get("candidates", []) if isinstance(c, dict) and "strategy_id" in c}
        for sid in sorted(registered):
            v = evaluate([p for p in by.get(sid, []) if (f(p.get("entry_time")) or 0) >= own[sid]], registry, today)
            L.append(f"- **{sid}**: {v['verdict']} ({v['positions']} positions)")
            L += [f"  - {a}: {b} -> {c}" for a, b, c in v["criteria"]]
    return "\n".join(L) + "\n", early


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", default=None)
    ap.add_argument("--registry", default=DEFAULT_REGISTRY)
    ap.add_argument("--out", default=DEFAULT_OUT)
    a = ap.parse_args(argv)
    export = a.export or sorted(glob.glob(os.path.join(DEFAULT_EXPORTS, "cloud_export_*")))[-1]
    today = dt.datetime.now(dt.timezone.utc).date()
    reg = load_registry(a.registry)
    text, early = build_report(load_jsonl(export, "paper_positions"), load_jsonl(export, "paper_scan_log"), reg, today)
    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, f"forward_{today:%Y%m%d}.md")
    if os.path.exists(path):                      # never overwrite an earlier report: add the time
        path = os.path.join(a.out, f"forward_{dt.datetime.now(dt.timezone.utc):%Y%m%d_%H%M%S}.md")
    with open(path, "x", encoding="utf-8") as fh:
        fh.write(text)
    if not early:
        with open(LOOKS_LOG, "a", encoding="utf-8") as fh:
            fh.write(f"{dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} verdict report written: {path}\n")
    print(text)
    print("report file:", path)


if __name__ == "__main__":
    main()
