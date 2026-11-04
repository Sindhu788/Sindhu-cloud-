"""Scores the stored protocol runs (Step 18). No parameter is touched; the holdout is not read. Labels (rules also in docs/BACKTEST_PROTOCOL.md):
  INSUFFICIENT_DATA  fewer than MIN_TOTAL_TRADES trades, or fewer than MIN_WINDOWS walk-forward windows with MIN_WINDOW_TRADES trades each
  FAILED             pooled profit factor (after base costs) <= 1.0
  FRAGILE            pooled PF > 1.0 but at least one robustness criterion fails
  ROBUST             ALL of: PF >= 1.1 in >= 60 % of the qualifying windows; PF >= 1.1 in >= 60 % of the coins that have >= 30 trades (and at least 3
                     such coins); pooled PF > 1.0 at cost x1.5; pooled PF >= 1.1 at cost x1
  The multiple-testing note: with 42 strategies tested, about 2 will look "ROBUST" by luck at a 5 % level. Each strategy therefore also gets the
  t-statistic of its mean net R per trade and `bonferroni_ok` (t >= 3.24, the two-sided 5 %/42 threshold). A ROBUST label without bonferroni_ok must be
  treated as a CANDIDATE that needs the sealed holdout, not as proof.
Usage: python -m data_platform.protocol_analyze [out_dir] -> writes protocol_results.json and docs/BACKTEST_RESULTS.md (if --md is given)."""
import collections
import datetime as dt
import glob
import gzip
import json
import math
import os
import sys

import numpy as np

from data_platform import cost_model

MIN_TOTAL_TRADES = 300
MIN_WINDOWS = 6
MIN_WINDOW_TRADES = 30
N_WINDOWS = 8
PF_BAR = 1.1
SHARE_BAR = 0.6
BONFERRONI_T = 3.24


def pf(pnls):
    p = np.asarray(pnls, dtype=float)
    gp, gl = p[p > 0].sum(), -p[p < 0].sum()
    return float(gp / gl) if gl > 0 else (float("inf") if gp > 0 else 0.0)


def load_runs(out_dir):
    runs = collections.defaultdict(dict)
    for path in glob.glob(os.path.join(out_dir, "trades", "*", "*.json.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            d = json.load(f)
        runs[d["strategy_id"]][d["symbol"]] = d
    return runs


def analyze_strategy(sid, by_coin, start_ms, end_ms, edges):
    trades = []
    for sym, d in by_coin.items():
        for t, net in zip(d["trades"], cost_model.reprice(d["trades"], 1.0)):
            trades.append((t["entry_time"], t["exit_time"], sym, t["side"], net, t.get("risk_amount") or 0.0, t))
    trades.sort(key=lambda x: x[1])
    n = len(trades)
    res = {"strategy_id": sid, "trades": n, "coins_run": len(by_coin)}
    if n == 0:
        res.update(label="INSUFFICIENT_DATA", reason="no trades")
        return res
    allt = [x[6] for x in trades]
    net1 = np.array([x[4] for x in trades])
    res["win_rate"] = round(100 * float((net1 > 0).mean()), 1)
    res["pf_x1"] = pf(net1)
    res["pf_x1_5"] = pf(cost_model.reprice(allt, 1.5))
    res["pf_x2"] = pf(cost_model.reprice(allt, 2.0))
    res["pf_gross"] = pf(cost_model.reprice(allt, 0.0))
    res["expectancy"] = round(float(net1.mean()), 4)
    r = np.array([x[4] / x[5] for x in trades if x[5]])
    res["avg_R"] = round(float(r.mean()), 4) if len(r) else None
    res["t_stat"] = round(float(r.mean() / (r.std(ddof=1) / math.sqrt(len(r)))), 2) if len(r) > 2 and r.std(ddof=1) > 0 else 0.0
    res["bonferroni_ok"] = bool(res["t_stat"] >= BONFERRONI_T)
    eq = np.cumsum(net1)
    res["max_drawdown"] = round(float((np.maximum.accumulate(eq) - eq).max()), 2)
    res["net_total"] = round(float(net1.sum()), 2)
    for side in ("long", "short"):
        s = [x[4] for x in trades if x[3] == side]
        res[f"{side}_n"], res[f"{side}_pf"] = len(s), (round(pf(s), 2) if s else None)
    # walk-forward windows (by entry time), pooled over coins
    w_rows = []
    for i in range(len(edges) - 1):
        w = [x[4] for x in trades if edges[i] <= x[0] < edges[i + 1]]
        w_rows.append({"n": len(w), "pf": pf(w) if w else None})
    qual = [w for w in w_rows if w["n"] >= MIN_WINDOW_TRADES]
    res["windows"] = [(w["n"], None if w["pf"] is None else round(min(w["pf"], 99), 2)) for w in w_rows]
    res["windows_qualifying"] = len(qual)
    res["windows_pf_ok"] = sum(1 for w in qual if w["pf"] >= PF_BAR)
    # per coin
    coin_rows = {}
    for sym in by_coin:
        c = [x[4] for x in trades if x[2] == sym]
        coin_rows[sym] = (len(c), pf(c) if c else None)
    cq = {k: v for k, v in coin_rows.items() if v[0] >= MIN_WINDOW_TRADES}
    res["coins_qualifying"] = len(cq)
    res["coins_pf_ok"] = sum(1 for v in cq.values() if v[1] >= PF_BAR)
    # hour-of-day split (UTC, 6-hour blocks)
    blocks = {}
    for b in range(4):
        h = [x[4] for x in trades if (dt.datetime.fromtimestamp(x[0] / 1000, dt.timezone.utc).hour // 6) == b]
        blocks[f"{b * 6:02d}-{b * 6 + 5:02d}"] = (len(h), round(min(pf(h), 99), 2) if h else None)
    res["hour_blocks"] = blocks
    # label
    if n < MIN_TOTAL_TRADES or res["windows_qualifying"] < MIN_WINDOWS:
        res["label"], res["reason"] = "INSUFFICIENT_DATA", f"{n} trades, {res['windows_qualifying']} qualifying windows"
    elif res["pf_x1"] <= 1.0:
        res["label"], res["reason"] = "FAILED", f"pooled PF {res['pf_x1']:.2f} after costs"
    else:
        ok_w = res["windows_pf_ok"] / res["windows_qualifying"] >= SHARE_BAR
        ok_c = res["coins_qualifying"] >= 3 and res["coins_pf_ok"] / res["coins_qualifying"] >= SHARE_BAR
        ok_pf = res["pf_x1"] >= PF_BAR and res["pf_x1_5"] > 1.0
        if ok_w and ok_c and ok_pf:
            res["label"], res["reason"] = "ROBUST", "consistent across windows and coins and survives x1.5 costs"
        else:
            why = [t for t, ok in (("windows", ok_w), ("coins", ok_c), ("pf/cost", ok_pf)) if not ok]
            res["label"], res["reason"] = "FRAGILE", "fails: " + ", ".join(why)
    return res


def main(argv):
    out_dir = argv[0] if argv and not argv[0].startswith("--") else os.path.join(os.environ.get("SINDHU_DATA_ROOT", r"D:\sindhu_data"), "experiments")
    runs = load_runs(out_dir)
    if not runs:
        print("no runs"); return
    any_run = next(iter(next(iter(runs.values())).values()))
    start_ms, end_ms = min(d["start_ms"] for r in runs.values() for d in r.values()), any_run["end_ms"]
    edges = [int(start_ms + (end_ms - start_ms) * i / N_WINDOWS) for i in range(N_WINDOWS + 1)]
    names = {s["id"]: s for s in json.load(open(os.path.join(out_dir, "strategies_42.json"), encoding="utf-8"))}
    results = []
    for sid, by_coin in sorted(runs.items()):
        r = analyze_strategy(sid, by_coin, start_ms, end_ms, edges)
        r["name"], r["group"], r["entry_tf"] = names.get(sid, {}).get("name"), names.get(sid, {}).get("group"), names.get(sid, {}).get("entry_tf")
        results.append(r)
    json.dump({"window_edges_ms": edges, "dev_start_ms": start_ms, "holdout_start_ms": end_ms, "results": results}, open(os.path.join(out_dir, "protocol_results.json"), "w"), indent=1, default=str)
    cnt = collections.Counter(r["label"] for r in results)
    print(dict(cnt))
    for r in sorted(results, key=lambda r: ({"ROBUST": 0, "FRAGILE": 1, "FAILED": 2, "INSUFFICIENT_DATA": 3}[r["label"]], -(r.get("pf_x1") or 0))):
        print(f"{r['label']:18s} {str(r['name'])[:44]:44s} tf={r['entry_tf']:>3} n={r['trades']:5d} PF={r.get('pf_x1', 0):5.2f} PFx1.5={r.get('pf_x1_5', 0):5.2f} "
              f"win={r.get('windows_pf_ok', 0)}/{r.get('windows_qualifying', 0)} coins={r.get('coins_pf_ok', 0)}/{r.get('coins_qualifying', 0)} t={r.get('t_stat', 0)}")


if __name__ == "__main__":
    main(sys.argv[1:])
