"""Day 6 Step 6/8/9: applies the rigour layer (data_platform/rigor.py) to the stored protocol runs. Reads trades + the development-window 1m candles
(never the sealed holdout), writes `protocol_rigor.json`. Run AFTER protocol_run:  python -m data_platform.protocol_rigor [--sims 500] [--coins 50]

Per strategy (pooled over the coins it traded):
- profit factor and mean money per position with 95 % cluster-bootstrap intervals (clusters = exit day, all coins together)
- RANDOM-ENTRY NULL: same positions count, side mix, holding times per coin, same round-trip costs, random entry times. Strategy net return per position
  (fraction of notional, fill-price based minus 2 x commission) vs the null distribution -> one-sided p-value; Benjamini-Hochberg FDR over strategies
- BASELINES under the same costs: SMA(20/50) crossover on 4h, RSI(14) < 30 / > 50 reversion on 1h (mean net return per trade, pooled over the same
  coins), and buy-and-hold (mean net total return of the same coins)
- FINAL LABEL = protocol_analyze label, downgraded ROBUST -> FRAGILE unless ALL of: PF CI lower bound > 1, null p < 0.05 and FDR pass, mean net return
  per position above both trade-based baselines.
"""
import argparse
import hashlib
import json
import os
import sys
import time

import numpy as np

from data_platform import metrics, protocol_analyze, resample, rigor

BASELINE_COST_NOTE = "baseline round trip = 2 x (commission + spread + slippage) of the coin's cost settings"


def rt_cost_pct(costs):
    return 2.0 * (costs["commission_pct"] + costs["spread_pct"] + costs["slippage_pct"])


def coin_baselines(arrays, costs):
    rt = rt_cost_pct(costs)
    t, c = arrays["open_time"], arrays["close"]
    h4, h1 = resample.resample(arrays, "4h"), resample.resample(arrays, "1h")
    return {"buy_hold": rigor.buy_and_hold(c, rt)["return"],
            "sma_4h": rigor.sma_cross_4h(h4["close"], rt), "rsi_1h": rigor.rsi_reversion_1h(h1["close"], rt)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--sims", type=int, default=500)
    ap.add_argument("--out", default=None)
    ap.add_argument("--only", default="", help="comma list of strategy ids (for testing)")
    a = ap.parse_args(argv)
    from data_platform.loader import CandleLoader
    out_dir = a.out or os.path.join(os.environ.get("SINDHU_DATA_ROOT", r"D:\sindhu_data"), "experiments")
    runs = protocol_analyze.load_runs(out_dir)
    if a.only:
        runs = {k: v for k, v in runs.items() if k in a.only.split(",")}
    loader = CandleLoader()
    hold = loader.holdout_start_ms
    some = next(iter(next(iter(runs.values())).values()))
    start_ms, end_ms = some["start_ms"], some["end_ms"]
    assert end_ms <= hold, "refusing to read candles inside the sealed holdout"
    coins = sorted({s for r in runs.values() for s in r})
    candles, base, costs = {}, {}, {}
    t0 = time.time()
    for s in coins:
        arr, _ = loader._load_1m(s, start_ms, end_ms)
        candles[s] = arr
        any_costs = next(r[s]["costs"] for r in runs.values() if s in r)
        costs[s] = any_costs
        base[s] = coin_baselines(arr, any_costs)
    print(f"loaded {len(coins)} coins + baselines in {time.time() - t0:.0f}s", flush=True)
    results = {}
    for si, (sid, by_coin) in enumerate(sorted(runs.items())):
        allpos, per_coin_null, n_by_coin, obs_sum = [], [], [], 0.0
        for sym, d in by_coin.items():
            pos = metrics.aggregate_positions([dict(t, symbol=sym) for t in d["trades"]])
            pos = [p for p in pos if p["ret"] is not None]
            if not pos:
                continue
            allpos += pos
            comm = d["costs"]["commission_pct"]
            net = np.array([p["ret"] - 2 * comm / 100.0 for p in pos])
            obs_sum += float(net.sum())
            dur = np.array([p["exit_time"] - p["entry_time"] for p in pos], dtype=np.int64)
            sides = np.array([1.0 if p["side"] == "long" else -1.0 for p in pos])
            nm = rigor.null_returns(candles[sym]["open_time"], candles[sym]["close"], dur, sides, rt_cost_pct(d["costs"]), n_sims=a.sims,
                                    seed=int(hashlib.sha256(f'{sid}/{sym}'.encode()).hexdigest()[:8], 16), window=(start_ms, end_ms))
            per_coin_null.append(nm * len(pos)); n_by_coin.append(len(pos))
        r = {"strategy_id": sid, "positions": len(allpos)}
        if allpos:
            pooled_null = np.sum(per_coin_null, axis=0) / sum(n_by_coin)
            obs = obs_sum / len(allpos)
            boot = rigor.cluster_bootstrap([p["pnl"] for p in allpos], [p["exit_time"] // 86_400_000 for p in allpos], n_boot=1000, seed=7)
            bs = [base[s] for s in by_coin if s in base]
            sma_n = sum(b["sma_4h"]["trades"] for b in bs); rsi_n = sum(b["rsi_1h"]["trades"] for b in bs)
            r.update(obs_mean_net_pct=round(100 * obs, 4), null_mean_pct=round(100 * float(pooled_null.mean()), 4),
                     null_p95_pct=round(100 * float(np.percentile(pooled_null, 95)), 4), null_p=round(rigor.one_sided_p(obs, pooled_null), 4),
                     pf=round(boot["pf"], 3), pf_ci=[round(x, 3) for x in boot["pf_ci"]], mean_money=round(boot["mean"], 3),
                     mean_money_ci=[round(x, 3) for x in boot["mean_ci"]], day_clusters=boot["clusters"],
                     sma4h_mean_net_pct=round(100 * sum(b["sma_4h"]["mean_net"] * b["sma_4h"]["trades"] for b in bs) / max(sma_n, 1), 4), sma4h_trades=sma_n,
                     rsi1h_mean_net_pct=round(100 * sum(b["rsi_1h"]["mean_net"] * b["rsi_1h"]["trades"] for b in bs) / max(rsi_n, 1), 4), rsi1h_trades=rsi_n,
                     buy_hold_mean_return_pct=round(100 * float(np.mean([b["buy_hold"] for b in bs])), 2), coins=len(bs))
        results[sid] = r
        if (si + 1) % 5 == 0:
            print(f"rigor {si + 1}/{len(runs)} strategies, {time.time() - t0:.0f}s", flush=True)
    ids = [k for k, v in results.items() if "null_p" in v]
    keep = rigor.bh_fdr([results[k]["null_p"] for k in ids], 0.05)
    for k, ok in zip(ids, keep):
        results[k]["fdr_pass"] = bool(ok)
    json.dump({"sims": a.sims, "note": BASELINE_COST_NOTE, "results": results}, open(os.path.join(out_dir, "protocol_rigor.json"), "w"), indent=1)
    print(f"done: {len(results)} strategies, {sum(1 for v in results.values() if v.get('fdr_pass'))} pass FDR, {time.time() - t0:.0f}s")


def final_label(base_label, rig):
    """ROBUST only when the extra evidence agrees; otherwise ROBUST is downgraded to FRAGILE. Other labels are kept."""
    if base_label != "ROBUST":
        return base_label
    ok = (rig.get("pf_ci", [0, 0])[0] > 1.0 and rig.get("null_p", 1) < 0.05 and rig.get("fdr_pass") is True
          and rig.get("obs_mean_net_pct", -1) > max(rig.get("sma4h_mean_net_pct", 0), rig.get("rsi1h_mean_net_pct", 0)))
    return "ROBUST" if ok else "FRAGILE"


if __name__ == "__main__":
    main()
