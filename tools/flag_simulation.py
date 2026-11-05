"""Day 7 Step 11: simulated effect of the OFF flags on the public signals actually sent (Cloud export). Rules applied in time order; the opposite-direction
rule only counts signals that would themselves have been sent in that scenario. Read-only. Usage: python tools/flag_simulation.py <export_folder>"""
import datetime as dt, json, sys, itertools
D = sys.argv[1]
L = lambda t: [json.loads(l) for l in open(f"{D}\{t}.jsonl", encoding="utf-8")]
pos = {p["id"]: p for p in L("paper_positions")}
conf = {r["position_id"]: float(r["confluence_ratio"]) for r in L("confluence_score_log")}
sent = sorted([r for r in L("telegram_message_log") if r["trigger_type"] == "automatic" and str(r["success"]) in ("True", "true", "1")], key=lambda r: r["sent_at"])
rows = []
for r in sent:
    p = pos[r["position_id"]]
    e, sl, tp = float(p["entry_price"]), float(p["stop_loss"]), float(p["take_profit"])
    rows.append(dict(i=len(rows) + 1, t=dt.datetime.fromisoformat(r["sent_at"]), sym=p["symbol"], side=p["direction"], tf=p["timeframe"], ratio=abs(tp - e) / abs(e - sl), engine=conf.get(r["position_id"], 1.0)))
def run(ro=(), gate=False, cap=None, opp=None):
    kept = []
    for a in rows:
        if a["tf"] in ro: continue
        if gate and a["engine"] < 1.0: continue
        if cap and a["ratio"] > cap: continue
        if opp and any(b["sym"] == a["sym"] and b["side"] != a["side"] and 0 <= (a["t"] - b["t"]).total_seconds() <= opp * 60 for b in kept): continue
        kept.append(a)
    return kept
scen = [("today (nothing changed)", {}), ("research-only 1m", dict(ro=("1m",))), ("research-only 1m,3m,5m", dict(ro=("1m", "3m", "5m"))),
        ("gate fix (real exchange)", dict(gate=True)), ("target cap 5", dict(cap=5)), ("opposite block 30 min", dict(opp=30)), ("opposite block 360 min", dict(opp=360)),
        ("hide confidence", {}), ("gate fix + research-only 1m,3m,5m", dict(gate=True, ro=("1m", "3m", "5m"))),
        ("ALL: research-only + gate + cap 5 + opposite 30", dict(gate=True, ro=("1m", "3m", "5m"), cap=5, opp=30))]
print("| Setting | Signals that would still have been sent (of 12) | Which (#) |"); print("|---|---|---|")
for name, kw in scen:
    k = run(**kw)
    print(f"| {name} | {len(k)} | {', '.join(str(a['i']) for a in k) or 'none'} |")
