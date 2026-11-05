"""Independent, read-only recomputation of trade metrics from the raw stored trades (Day 6 Step 4).
Deliberately does NOT import anything from data_platform: plain numpy only.
Usage: python tools/recompute_metrics.py <strategy_id> [experiments_dir]"""
import glob, gzip, json, math, os, sys
import numpy as np

def load(sid, d=r"D:\sindhu_data\experiments"):
    rows = []
    for f in sorted(glob.glob(os.path.join(d, "trades", sid, "*.json.gz"))):
        j = json.load(gzip.open(f, "rt"))
        for t in j["trades"]:
            t = dict(t); t["symbol"] = j["symbol"]; rows.append(t)
    return rows

def stats(pnl):
    p = np.asarray(pnl, float); n = len(p)
    if n == 0: return {"n": 0}
    gp, gl = p[p > 0].sum(), -p[p < 0].sum()
    sd = p.std(ddof=1) if n > 2 else float("nan")
    return {"n": n, "win%": round(100 * (p > 0).mean(), 1), "sum": round(p.sum(), 2), "mean": round(p.mean(), 4),
            "pf": round(gp / gl, 4) if gl > 0 else float("inf"), "t": round(p.mean() / (sd / math.sqrt(n)), 2) if sd == sd and sd > 0 else None}

if __name__ == "__main__":
    sid = sys.argv[1]; rows = load(sid, *(sys.argv[2:3]))
    pnl = np.array([t["pnl"] for t in rows]); risk = np.array([t.get("risk_amount") or 0.0 for t in rows])
    print("trades", len(rows), "partial", sum(bool(t.get("is_partial")) for t in rows), "risk==0:", int((risk == 0).sum()))
    print("risk_amount quantiles (0,5,25,50,75,95,100%):", np.round(np.percentile(risk[risk > 0], [0, 5, 25, 50, 75, 95, 100]), 4).tolist())
    print("dollar net      :", stats(pnl))
    print("dollar gross    :", stats([t["gross_pnl"] for t in rows]))
    m = risk > 0
    print("R = pnl/risk    :", stats(pnl[m] / risk[m]))
    print("sum(pnl)/sum(risk) (R-equivalent of the dollar result):", round(pnl[m].sum() / risk[m].sum(), 4))
    cost = np.array([(t.get("commission_cost") or 0) + (t.get("slippage_cost") or 0) + (t.get("spread_cost") or 0) for t in rows])
    print("avg cost/trade $", round(cost.mean(), 4), "| avg cost in R", round((cost[m] / risk[m]).mean(), 4), "| median cost in R", round(float(np.median(cost[m] / risk[m])), 4))
    ex = {}
    for t in rows: ex.setdefault(t.get("exit_reason"), []).append(t["pnl"])
    print("by exit reason:", {k: (len(v), round(sum(v), 1)) for k, v in ex.items()})
    k = {(t["symbol"], t["entry_time"], t["exit_time"], t["side"]) for t in rows}
    print("duplicate (symbol, entry, exit, side):", len(rows) - len(k))


def positions(rows):
    """Group legs (partial take-profit + remainder) into one position: same symbol, side and entry time."""
    pos = {}
    for t in rows:
        pos.setdefault((t["symbol"], t["entry_time"], t["side"]), []).append(t)
    out = []
    for (sym, et, side), legs in pos.items():
        out.append({"symbol": sym, "entry_time": et, "exit_time": max(l["exit_time"] for l in legs), "pnl": sum(l["pnl"] for l in legs),
                    "risk": sum(l.get("risk_amount") or 0.0 for l in legs), "legs": len(legs)})
    out.sort(key=lambda x: x["exit_time"])
    return out

def summary(sid, d=r"D:\sindhu_data\experiments"):
    rows = load(sid, d)
    if not rows: return None
    legs = stats([t["pnl"] for t in rows])
    P = positions(rows)
    pp = [p["pnl"] for p in P]
    pr = [p["pnl"] / p["risk"] for p in P if p["risk"] > 0]
    lr = [t["pnl"] / t["risk_amount"] for t in rows if t.get("risk_amount")]
    return {"legs": len(rows), "positions": len(P), "leg_pf": legs["pf"], "pos_pf": stats(pp)["pf"], "pos_win%": stats(pp)["win%"],
            "leg_R_t": stats(lr)["t"], "pos_R_t": stats(pr)["t"], "pos_R_mean": stats(pr)["mean"], "sum$": stats(pp)["sum"]}
