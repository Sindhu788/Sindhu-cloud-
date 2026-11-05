"""Day 7 Step 12: parameter sensitivity of Ichimoku 1d Indicator-Exit (analysis only; nothing in the real strategy library or code is changed).
Variants live in a scratch library inside the output folder; the Ichimoku periods are changed only inside this process (function defaults of
`concepts.ichimoku_cloud`), the stop buffer and take-profit multiple only in the copied JSON. One parameter at a time, at x0.8, x0.9, x1.1, x1.2.
Usage (venv with pandas + pyarrow):  python tools/ichimoku_sensitivity.py run [--workers 2] [--coins 50]   then   python tools/ichimoku_sensitivity.py report
Output folder: D:\\sindhu_data\\candidates\\ichimoku_sensitivity (new files only; existing results are skipped, never overwritten)."""
import copy
import datetime as dt
import json
import multiprocessing as mp
import os
import shutil
import sys

SID = "d781b37694ef"
SRC = r"D:\sindhu_runtime\strategy_library"
OUT = r"D:\sindhu_data\candidates\ichimoku_sensitivity"
LIB = os.path.join(OUT, "strategy_library")
os.environ["SINDHU_STRATEGY_LIBRARY_DIR"] = LIB
os.environ.setdefault("SINDHU_BACKTEST_SOURCE", "dataplatform")
os.environ.setdefault("SINDHU_DATA_DIR", r"D:\sindhu_runtime\dp_bt_data")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE_PERIODS = (9, 26, 52, 26)
SCALES = (0.8, 0.9, 1.1, 1.2)


def variants():
    v = [{"tag": "base", "periods": BASE_PERIODS, "stop": 0.65, "rr": 10.0, "param": "base", "scale": 1.0}]
    for sc in SCALES:
        v.append({"tag": f"periods_x{sc}", "periods": tuple(max(2, round(p * sc)) for p in BASE_PERIODS), "stop": 0.65, "rr": 10.0, "param": "ichimoku periods (9/26/52/26)", "scale": sc})
    for sc in SCALES:
        v.append({"tag": f"stop_x{sc}", "periods": BASE_PERIODS, "stop": round(0.65 * sc, 4), "rr": 10.0, "param": "stop buffer (0.65)", "scale": sc})
    for sc in SCALES:
        v.append({"tag": f"rr_x{sc}", "periods": BASE_PERIODS, "stop": 0.65, "rr": round(10.0 * sc, 4), "param": "take-profit multiple (10 R)", "scale": sc})
    return v


def vid(v):
    return f"{SID}~{v['tag']}"


def build_library():
    for v in variants():
        d = os.path.join(LIB, vid(v))
        if os.path.exists(d):
            continue
        shutil.copytree(os.path.join(SRC, SID), d)
        meta = json.load(open(os.path.join(d, "meta.json"), encoding="utf-8")); meta["id"] = vid(v)
        json.dump(meta, open(os.path.join(d, "meta.json"), "w", encoding="utf-8"), indent=1)
        vp = os.path.join(d, "versions", "v1.json")
        cfg = json.load(open(vp, encoding="utf-8"))
        cfg["stop_loss"]["value"] = v["stop"]; cfg["take_profit"]["value"] = v["rr"]
        json.dump(cfg, open(vp, "w", encoding="utf-8"), indent=1)


def _job(job):
    v, args = job
    from backtest_engine import concepts
    concepts.ichimoku_cloud.__defaults__ = tuple(v["periods"])
    from data_platform import protocol_run
    sid, symbol, rank, start_ms, end_ms, out_dir = args
    return protocol_run.run_one((vid(v), symbol, rank, start_ms, end_ms, out_dir))


def run(workers=2, coins=50):
    from data_platform import backtest_source, store, universe
    os.makedirs(OUT, exist_ok=True)
    build_library()
    root = store.root(); L = backtest_source.loader(); hold = L.holdout_start_ms
    first = min(int(x["first_ts"]) for k, x in L.manifest.snapshot().items() if x.get("status") == "ok" and len(k.split("/")) == 2 and len(k.split("/")[1]) == 7)
    syms = universe.load_latest(root)["symbols"][:coins]
    jobs = [(v, (SID, s, r + 1, first, hold, OUT)) for v in variants() for r, s in enumerate(syms)]
    print(f"{len(jobs)} runs ({len(variants())} variants x {len(syms)} coins), window up to {dt.datetime.fromtimestamp(hold / 1000, dt.timezone.utc):%Y-%m-%d} (holdout sealed)", flush=True)
    done = 0
    with mp.Pool(workers) as pool:
        for res in pool.imap_unordered(_job, jobs):
            done += 1
            if done % 25 == 0:
                print(f"{done}/{len(jobs)}", flush=True)
    print("finished", done, flush=True)


def report():
    import numpy as np
    from data_platform import cost_model, metrics, protocol_analyze, rigor
    runs = protocol_analyze.load_runs(OUT)
    any_run = next(iter(next(iter(runs.values())).values()))
    start_ms, end_ms = min(d["start_ms"] for r in runs.values() for d in r.values()), any_run["end_ms"]
    edges = [int(start_ms + (end_ms - start_ms) * i / protocol_analyze.N_WINDOWS) for i in range(protocol_analyze.N_WINDOWS + 1)]
    rows = []
    for v in variants():
        by = runs.get(vid(v), {})
        if not by:
            continue
        r = protocol_analyze.analyze_strategy(vid(v), by, start_ms, end_ms, edges)
        pos = [p for sym, d in by.items() for p in metrics.aggregate_positions([dict(t, symbol=sym) for t in d["trades"]])]
        boot = rigor.cluster_bootstrap([p["pnl"] for p in pos], [p["exit_time"] // 86_400_000 for p in pos], n_boot=1000, seed=3) if pos else None
        rows.append((v, r, boot))
    print("| Parameter | Scale | Value | Positions | PF x1 [95 % CI] | PF x1.5 | PF x2 | PF gross | Win % | Windows ok | Label |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for v, r, b in rows:
        val = v["periods"] if v["param"].startswith("ichimoku") else (v["stop"] if v["param"].startswith("stop") else (v["rr"] if v["param"].startswith("take") else "base"))
        ci = f"[{b['pf_ci'][0]:.2f}-{b['pf_ci'][1]:.2f}]" if b else ""
        print(f"| {v['param']} | x{v['scale']} | {val} | {r['trades']} | {r.get('pf_x1', 0):.2f} {ci} | {r.get('pf_x1_5', 0):.2f} | {r.get('pf_x2', 0):.2f} | {r.get('pf_gross', 0):.2f} | {r.get('win_rate')} | {r.get('windows_pf_ok', 0)}/{r.get('windows_qualifying', 0)} | {r['label']} |")
    # base-case detail: per coin, per window, long/short, concentration, leave-one-coin-out
    base_v = variants()[0]
    by = runs[vid(base_v)]
    allpos = []
    percoin = {}
    for sym, d in by.items():
        ps = metrics.aggregate_positions([dict(t, symbol=sym) for t in d["trades"]])
        net = cost_model.reprice(ps, 1.0)
        percoin[sym] = (len(ps), float(sum(net)), metrics.profit_factor(net) if ps else 0.0)
        allpos += list(zip(ps, net))
    tot = sum(n for _, n in allpos)
    print(f"\nBASE: positions {len(allpos)}, net {tot:.1f}; coins with trades {sum(1 for c in percoin.values() if c[0])}; coins with positive net {sum(1 for c in percoin.values() if c[1] > 0)}; coins with >= 5 positions {sum(1 for c in percoin.values() if c[0] >= 5)}")
    best = sorted(percoin.items(), key=lambda kv: -kv[1][1])[:5]
    print("top 5 coins by net:", [(k, v[0], round(v[1], 1)) for k, v in best], "| their share of total net:", round(sum(v[1] for _, v in best) / tot, 2) if tot else None)
    loo = []
    for sym in percoin:
        rest = [n for (p, n) in allpos if p["symbol"] != sym]
        loo.append(metrics.profit_factor(rest))
    print("leave-one-coin-out PF: min %.2f median %.2f max %.2f" % (min(loo), float(np.median(loo)), max(loo)))
    for i in range(protocol_analyze.N_WINDOWS):
        w = [n for (p, n) in allpos if edges[i] <= p["entry_time"] < edges[i + 1]]
        print(f"window {i + 1}: {dt.datetime.fromtimestamp(edges[i] / 1000, dt.timezone.utc):%Y-%m-%d}  positions {len(w):3d}  PF {metrics.profit_factor(w):.2f}  net {sum(w):.1f}")
    for side in ("long", "short"):
        s = [n for (p, n) in allpos if p["side"] == side]
        print(f"{side}: positions {len(s)}, PF {metrics.profit_factor(s):.2f}, net {sum(s):.1f}")
    hold_days = np.array([(p["exit_time"] - p["entry_time"]) / 86_400_000 for p, _ in allpos])
    print(f"holding time (days): median {np.median(hold_days):.1f}, mean {hold_days.mean():.1f}, max {hold_days.max():.0f}")
    ex = {}
    for p, n in allpos:
        pass
    wins = np.array([n for _, n in allpos]); print(f"avg win {wins[wins > 0].mean():.2f}, avg loss {wins[wins < 0].mean():.2f}, largest win {wins.max():.1f} (share of gross profit {wins.max() / wins[wins > 0].sum():.2f})")


if __name__ == "__main__":
    mp.freeze_support()
    if len(sys.argv) > 1 and sys.argv[1] == "report":
        report()
    else:
        w = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 2
        c = int(sys.argv[sys.argv.index("--coins") + 1]) if "--coins" in sys.argv else 50
        run(w, c)
