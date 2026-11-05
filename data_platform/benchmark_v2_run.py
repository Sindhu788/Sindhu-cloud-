"""Master plan B4 (job BT-RUN): runs EXACTLY the pre-registered units for both V2 strategies and writes one JSON result + a .done marker
(SHA-256 of the result) per unit into D:\\sindhu_runtime\\bt_jobs\\BT-RUN. A rerun skips units whose marker matches. Then it applies the
verdict rules of docs/BENCHMARK_PREREGISTRATION_V2.md section 3 and writes verdicts.json.

Units per strategy: base (costs x1), gross (costs 0, for cost drag), stress (costs x1.5), 8 neighbours; plus 2 benchmarks.
No parameter search: the neighbour list is the fixed one from the pre-registration. Data ends 2026-10-31 (forward test never used).
Usage (bt venv):  python -m data_platform.benchmark_v2_run [--job-dir ...]"""
import argparse
import datetime as dt
import hashlib
import json
import os
import threading

import numpy as np

from data_platform import benchmark_v2 as bv

PERIODS = {"IS": (bv.IS_START, bv.IS_END), "OOS": (bv.OOS_START, bv.OOS_END)}
WF = {str(y): (f"{y}-01-01", f"{y}-12-31" if y < 2026 else bv.OOS_END) for y in bv.WF_YEARS}


def _summ(res):
    out = {}
    for k, (a, b) in list(PERIODS.items()) + [("WF_" + y, v) for y, v in WF.items()] + [("FULL", (bv.IS_START, bv.OOS_END))]:
        m = bv.metrics(res, a, b)
        if m is not None:
            m.pop("_returns", None)
        out[k] = m
    out["pooled_pf_full"] = bv.pooled_pf(res)
    years = (len(res["days"]) / 365.0) or 1
    start_eq = 100.0
    out["turnover_per_year_x"] = round(res["turnover"] / start_eq / years, 2)     # approximate: relative to the starting capital
    out["costs_paid"] = round(res["costs"], 4)
    return out


class Job:
    def __init__(self, job_dir):
        self.dir = job_dir
        os.makedirs(job_dir, exist_ok=True)
        self.hb = os.path.join(job_dir, "heartbeat.txt")
        self._stop = threading.Event()

    def log(self, msg):
        line = f"{dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M:%S} {msg}"
        print(line, flush=True)
        with open(os.path.join(self.dir, "job.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def beat(self, note):
        with open(self.hb, "w", encoding="utf-8") as f:
            f.write(f"{dt.datetime.now(dt.timezone.utc).isoformat()} {note}\n")

    def unit(self, name, fn):
        path = os.path.join(self.dir, f"{name}.json")
        marker = path + ".done"
        if os.path.exists(marker) and os.path.exists(path) and open(marker).read().strip() == hashlib.sha256(open(path, "rb").read()).hexdigest():
            self.log(f"{name}: done earlier, hash verified")
            return json.load(open(path, encoding="utf-8"))
        res = fn()
        body = json.dumps(res, indent=1, sort_keys=True, default=float)
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            f.write(body)
        os.replace(path + ".tmp", path)
        with open(marker, "w") as f:
            f.write(hashlib.sha256(body.encode("utf-8")).hexdigest())
        self.beat(f"{name} done")
        self.log(f"{name}: written")
        return res

    def run(self):
        threading.Thread(target=lambda: [self.beat("alive") for _ in iter(lambda: self._stop.wait(60), True)], daemon=True).start()
        p = bv.Panel.from_parquet()
        self.log(f"panel: {len(p.days)} days x {len(p.symbols)} coins")
        results = {}
        keep = {}
        for strat in ("donchian", "tsmom"):
            def base():
                r = bv.run_strategy(p, strat)
                keep[(strat, "base")] = r
                s = _summ(r)
                oos = bv.metrics(r, *PERIODS["OOS"])
                s["oos_block_bootstrap_p"] = bv.block_bootstrap_p(oos["_returns"])
                a, b = bv._ms(bv.IS_START), bv._ms(bv.OOS_END)
                s["position_return_ci95_pct"] = bv.position_bootstrap_ci([x["ret"] for x in r["positions"] if a <= x["entry_day"] <= b])
                s["equity"] = [round(float(x), 4) for x in r["equity"]]
                return s
            results[(strat, "base")] = self.unit(f"{strat}__base", base)
            results[(strat, "gross")] = self.unit(f"{strat}__gross_costs0", lambda: _summ(bv.run_strategy(p, strat, cost=0.0)))
            results[(strat, "stress")] = self.unit(f"{strat}__costs_x1_5", lambda: _summ(bv.run_strategy(p, strat, cost=bv.COST * 1.5)))
            for label, params in bv.neighbours(strat):
                key = label.replace(" ", "_")
                results[(strat, label)] = self.unit(f"{strat}__nb_{key}", lambda params=params: _summ(bv.run_strategy(p, strat, params)))
        def bench(fn):
            def f():
                r = fn(p)
                s = _summ(r)
                s["equity"] = [round(float(x), 4) for x in r["equity"]]
                return s
            return f
        results[("bench", "btc")] = self.unit("bench__btc_buy_hold", bench(bv.btc_buy_hold))
        results[("bench", "ew")] = self.unit("bench__equal_weight", bench(bv.equal_weight_buy_hold))
        verdicts = self.verdicts(results)
        with open(os.path.join(self.dir, "verdicts.json"), "w", encoding="utf-8") as f:
            json.dump(verdicts, f, indent=1, default=float)
        self.log("ALL-DONE " + json.dumps({k: v["verdict"] for k, v in verdicts.items()}))
        open(os.path.join(self.dir, "ALL.done"), "w").write("ok")
        self._stop.set()

    @staticmethod
    def verdicts(results):
        rig = json.load(open(r"D:\sindhu_data\experiments\protocol_rigor.json", encoding="utf-8"))["results"]
        existing_p = [float(v.get("null_p")) for v in rig.values() if v.get("null_p") is not None]
        out = {}
        new_p = {s: results[(s, "base")]["oos_block_bootstrap_p"] for s in ("donchian", "tsmom")}
        allp = existing_p + [new_p["donchian"], new_p["tsmom"]]
        passing = bv.benjamini_hochberg(allp, q=0.05)
        n_exist = len(existing_p)
        bench_sharpe = max(results[("bench", "btc")]["OOS"]["sharpe"], results[("bench", "ew")]["OOS"]["sharpe"])
        for k, s in enumerate(("donchian", "tsmom")):
            b = results[(s, "base")]
            oos, ins, full = b["OOS"], b["IS"], b["FULL"]
            wf = [b["WF_" + y] for y in WF if b.get("WF_" + y)]
            wf_pos = sum(1 for m in wf if m["total_return_pct"] > 0)
            wf_total = float(np.prod([1 + m["total_return_pct"] / 100 for m in wf]) - 1) * 100
            nb = [results[(s, lab)]["OOS"]["total_return_pct"] for lab, _ in bv.neighbours(s)]
            pf1 = b["pooled_pf_full"]
            pf15 = results[(s, "stress")]["pooled_pf_full"]
            checks = {
                "1 OOS return > 0 and Sharpe > 0": oos["total_return_pct"] > 0 and oos["sharpe"] > 0,
                "2 IS return > 0": ins["total_return_pct"] > 0,
                "3 walk-forward >= 4 of 6 years positive and combined > 0": wf_pos >= 4 and wf_total > 0,
                "4 OOS Sharpe >= better benchmark - 0.05": oos["sharpe"] >= bench_sharpe - 0.05,
                "5 no neighbour OOS return <= 0": all(x > 0 for x in nb),
                "6 pooled PF >= 1.1 at x1 and > 1.0 at x1.5": pf1 >= 1.1 and pf15 > 1.0,
                f"7 BH q=0.05 over {len(allp)} tests": (n_exist + k) in passing,
            }
            insufficient = full["positions"] < 300 or oos["positions"] < 30 or oos["coins_with_positions"] < 5
            failed = oos["total_return_pct"] <= 0 or pf1 <= 1.0
            if insufficient:
                verdict = "INSUFFICIENT_DATA"
            elif failed:
                verdict = "FAILED"
            elif all(checks.values()):
                verdict = "ROBUST"
            else:
                verdict = "FRAGILE"
            out[s] = {"verdict": verdict, "checks": checks, "oos_p": new_p[s], "bench_best_oos_sharpe": bench_sharpe,
                      "wf_positive_years": wf_pos, "wf_combined_return_pct": round(wf_total, 2), "neighbour_oos_returns_pct": nb,
                      "pooled_pf_x1": pf1, "pooled_pf_x1_5": pf15, "positions_full": full["positions"], "positions_oos": oos["positions"]}
        return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--job-dir", default=r"D:\sindhu_runtime\bt_jobs\BT-RUN")
    Job(ap.parse_args().job_dir).run()
