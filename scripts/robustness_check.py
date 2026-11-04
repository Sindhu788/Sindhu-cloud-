"""Read-only robustness check (Day 4): rolling windows + parameter sensitivity for given strategies. Nothing is saved to the strategy
library and no parameter is ever applied: every variant is a clone used for one in-memory backtest.
Usage: python scripts/robustness_check.py <out.json> <strategy_id> [<strategy_id> ...]
Env: SINDHU_DATA_DIR must point to a throwaway copy that holds 1m candles (default D:/sindhu_runtime/wf_data)."""
import json
import os
import sys
import time

os.environ.setdefault("SINDHU_DATA_DIR", "D:/sindhu_runtime/wf_data")
os.environ.setdefault("SINDHU_STRATEGY_LIBRARY_DIR", "D:/sindhu_runtime/strategy_library")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from automation_pipeline import optimizer
from backtest_engine import strategy_library
from data_engine import storage

EXCHANGE = "binance"
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
SETTINGS = {"initial_balance": 1000.0, "commission_pct": 0.1, "slippage_pct": 0.05, "position_size_pct": 10.0}
out_path, ids = sys.argv[1], sys.argv[2:]

with storage.get_conn() as c:
    lo, hi = c.execute("SELECT MIN(open_time), MAX(open_time) FROM klines_1m").fetchone()
span = (hi - lo) / 4
WINDOWS = [(int(lo + i * span), int(lo + (i + 1) * span)) for i in range(4)]


def metrics(cfg, sym, a, b):
    t0 = time.time()
    try:
        m = optimizer._run_in_memory(cfg, EXCHANGE, sym, dict(SETTINGS, risk_pct=cfg.risk_pct or 1.0), a, b)
    except Exception as e:  # a variant can be invalid; report it, do not hide it
        return {"error": str(e)[:80]}
    print(f"   run {sym} {(b - a) / 86400000:.0f}d took {time.time() - t0:.0f}s", flush=True)
    if m is None:
        return None
    g = lambda k: m.get(k) if isinstance(m, dict) else getattr(m, k, None)
    return {"trades": g("total_trades"), "pf": g("profit_factor"), "net": g("total_pnl"), "win": g("win_rate")}


result = {}
for sid in ids:
    t0 = time.time()
    cfg = strategy_library.load(sid)
    rec = {"name": cfg.name, "windows": [], "sensitivity": []}
    for w, (a, b) in enumerate(WINDOWS):
        agg = {"trades": 0, "net": 0.0, "gp": 0.0, "gl": 0.0}
        per = {}
        for s in SYMS:
            m = metrics(cfg, s, a, b)
            per[s] = m
            if m and "error" not in m and m["trades"]:
                agg["trades"] += m["trades"]; agg["net"] += m["net"] or 0.0
        rec["windows"].append({"window": w + 1, "start_ms": a, "end_ms": b, "trades": agg["trades"], "net": round(agg["net"], 2), "per_coin": per})
    base = metrics(cfg, "BTCUSDT", lo, hi)
    rec["baseline_btc_full"] = base
    try:
        dims = optimizer.tunable_dimensions(cfg)
    except Exception as e:
        dims = []
        rec["sensitivity_error"] = str(e)[:80]
    for d in [d for d in dims if isinstance(d.get("baseline"), (int, float)) and d.get("candidates")][:3]:
        for factor in (0.8, 0.9, 1.1, 1.2):
            target = d["baseline"] * factor
            val = min(d["candidates"], key=lambda v: abs(v - target))
            if val == d["baseline"]:
                continue
            clone = optimizer._clone_config(cfg)
            try:
                d["apply"](clone, val)
            except Exception:
                continue
            m = metrics(clone, "BTCUSDT", lo, hi)
            rec["sensitivity"].append({"dim": d.get("description") or d.get("id"), "baseline": d["baseline"], "factor": factor, "value": val, "result": m})
    rec["seconds"] = round(time.time() - t0)
    result[sid] = rec
    json.dump(result, open(out_path, "w"), indent=1, default=str)
    print(f"done {sid} {cfg.name[:40]} in {rec['seconds']}s", flush=True)
