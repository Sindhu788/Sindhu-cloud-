r"""Master plan V2 PG5: compact copy of the Part B (V2 benchmark) results for the Backtests page: per strategy the FULL/IS/OOS and
walk-forward metrics, the verdict, and the equity curve sampled weekly. Source: D:\sindhu_runtime\bt_jobs\BT-RUN-v2 (reported run).
Output: paper_trading/benchmark_v2_summary.json (committed; no forward-test data, nothing after 2026-10-31)."""
import json
import os
from datetime import date, timedelta

SRC = r"D:\sindhu_runtime\bt_jobs\BT-RUN-v2"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "paper_trading", "benchmark_v2_summary.json")
UNITS = {"donchian__base": "Donchian Trend Ensemble (1d, long-only)", "tsmom__base": "Vol-scaled TSMOM (1d, weekly, long-only)",
         "bench__btc_buy_hold": "Benchmark: BTC buy-and-hold", "bench__equal_weight": "Benchmark: equal-weight universe"}


def main():
    verdicts = json.load(open(os.path.join(SRC, "verdicts.json"), encoding="utf-8"))
    out = {"source": "BT-RUN-v2 (reported run, docs/STRATEGY_V2_REPORT.md)", "preregistration": "docs/BENCHMARK_PREREGISTRATION_V2.md",
           "tests_in_fdr": 44, "units": []}
    for key, label in UNITS.items():
        d = json.load(open(os.path.join(SRC, key + ".json"), encoding="utf-8"))
        full = d["FULL"]
        start = date.fromisoformat(str(full["start"])[:10])
        eq = d.get("equity") or []
        pts = [[(start + timedelta(days=i)).isoformat(), round(v, 3)] for i, v in enumerate(eq) if i % 7 == 0 or i == len(eq) - 1]
        v = verdicts.get(key.split("__")[0]) if not key.startswith("bench") else None
        out["units"].append({"id": key, "name": label, "verdict": (v or {}).get("verdict") if isinstance(v, dict) else v,
                             "verdict_detail": v if isinstance(v, dict) else None,
                             "metrics": {k: d[k] for k in ("FULL", "IS", "OOS") if k in d},
                             "walk_forward": {k[3:]: d[k] for k in d if k.startswith("WF_")},
                             "oos_block_bootstrap_p": d.get("oos_block_bootstrap_p"), "pooled_pf_full": d.get("pooled_pf_full"),
                             "costs_paid": d.get("costs_paid"), "turnover_per_year_x": d.get("turnover_per_year_x"), "equity_weekly": pts})
    def clean(v):  # Infinity/NaN (e.g. a profit factor with no losing year) are not valid JSON: null = "not defined"
        if isinstance(v, float) and (v != v or v in (float("inf"), float("-inf"))):
            return None
        if isinstance(v, dict):
            return {k: clean(x) for k, x in v.items()}
        if isinstance(v, list):
            return [clean(x) for x in v]
        return v
    json.dump(clean(out), open(OUT, "w", encoding="utf-8"), separators=(",", ":"), allow_nan=False)
    print(OUT, os.path.getsize(OUT))


if __name__ == "__main__":
    main()
