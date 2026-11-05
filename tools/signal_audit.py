"""Day 7 Step 10: audit of every automatic public signal in a Cloud export folder against the Day 6 validated labels. Read-only.
Usage: python tools/signal_audit.py <export_folder> > table.md"""
import collections, datetime as dt, json, sys
sys.path.insert(0, ".")
from data_platform import protocol_rigor

D = sys.argv[1]
EXP = r"D:\sindhu_data\experiments"
L = lambda t: [json.loads(l) for l in open(f"{D}\{t}.jsonl", encoding="utf-8")]
res = {r["strategy_id"]: r for r in json.load(open(EXP + r"\protocol_results.json"))["results"]}
rig = json.load(open(EXP + r"\protocol_rigor.json"))["results"]
label = {k: protocol_rigor.final_label(r["label"], rig.get(k, {})) for k, r in res.items()}
pos = {p["id"]: p for p in L("paper_positions")}
grp = {g["strategy_id"]: g.get("group_key") for g in L("paper_strategy_groups")}
sent = sorted([r for r in L("telegram_message_log") if r["trigger_type"] == "automatic" and str(r["success"]) in ("True", "true", "1")], key=lambda r: r["sent_at"])
conf = {}
for r in L("confluence_score_log"): conf.setdefault(r["position_id"], []).append(float(r["confluence_ratio"]))
f = lambda x: float(x) if x not in (None, "") else None
rows = []
for r in sent:
    p = pos.get(r["position_id"], {})
    e, sl, tp = f(p.get("entry_price")), f(p.get("stop_loss")), f(p.get("take_profit"))
    ratio = abs(tp - e) / abs(e - sl) if e and sl and tp and e != sl else None
    t_sent = dt.datetime.fromisoformat(r["sent_at"]); t_open = dt.datetime.fromisoformat(p["created_at"]) if p.get("created_at") else None
    fresh = (t_sent - t_open).total_seconds() if t_open else None
    rows.append(dict(sent=r["sent_at"][:16].replace("T", " "), sym=p.get("symbol"), side=p.get("direction"), sid=r["strategy_id"], name=(r["strategy_name"] or "")[:34],
                     tf=p.get("timeframe"), label=label.get(r["strategy_id"], "not in the 42"), group=grp.get(r["strategy_id"], "?"), confidence=p.get("confidence"), ratio=ratio,
                     fresh=fresh, engine_conf=(conf.get(r["position_id"]) or [None])[0], status=p.get("status"), pnl=f(p.get("pnl")), exit=p.get("exit_reason"),
                     t_sent=t_sent, pid=r["position_id"], entry=e, grade=r.get("quality_grade")))
for a in rows:
    others = [b for b in rows if b is not a and b["sym"] == a["sym"] and b["side"] != a["side"]]
    near = min(others, key=lambda b: abs((b["t_sent"] - a["t_sent"]).total_seconds()), default=None)
    a["opp"] = f"{near['side']} {abs((near['t_sent'] - a['t_sent']).total_seconds()) / 3600:.1f} h {'later' if near['t_sent'] > a['t_sent'] else 'earlier'}" if near else "-"
print("| # | Sent (UTC) | Coin | Side | Strategy | TF | Day 6 label | Group | Conf. | Target/stop | Fresh (s) | Engine score at open | Opposite signal same coin | Regime tag shown | Outcome so far |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for i, a in enumerate(rows, 1):
    out = f"closed {a['exit']} {a['pnl']:+.2f}" if a["status"] == "closed" and a["pnl"] is not None else (a["status"] or "?")
    print(f"| {i} | {a['sent']} | {a['sym']} | {a['side']} | {a['name']} | {a['tf']} | {a['label']} | {a['group']} | {a['confidence']} | {a['ratio']:.1f} | {a['fresh']:.0f} | {a['engine_conf']:.3f} | {a['opp']} | none (not counted) | {out} |"
          if a["ratio"] is not None and a["fresh"] is not None and a["engine_conf"] is not None else f"| {i} | {a['sent']} | {a['sym']} | {a['side']} | {a['name']} | {a['tf']} | {a['label']} | {a['group']} | {a['confidence']} | {a['ratio']} | {a['fresh']} | {a['engine_conf']} | {a['opp']} | none (not counted) | {out} |")
n = len(rows)
print()
print(f"**Summary (n = {n} signals):**")
print("- by Day 6 label:", dict(collections.Counter(a["label"] for a in rows)))
print("- by entry timeframe:", dict(collections.Counter(a["tf"] for a in rows)))
print(f"- 1-minute timeframe: {sum(1 for a in rows if a['tf'] == '1m')} of {n}; 1m or 5m: {sum(1 for a in rows if a['tf'] in ('1m', '5m'))} of {n}")
print("- by strategy:", dict(collections.Counter(a['name'] for a in rows)))
print("- by group now:", dict(collections.Counter(a["group"] for a in rows)))
print(f"- target-to-stop above 5: {sum(1 for a in rows if a['ratio'] and a['ratio'] > 5)} of {n}; freshness at send (s): min {min(a['fresh'] for a in rows if a['fresh'] is not None):.0f}, max {max(a['fresh'] for a in rows if a['fresh'] is not None):.0f}")
cl = [a for a in rows if a["status"] == "closed" and a["pnl"] is not None]
print(f"- outcome so far: {len(cl)} closed (wins {sum(1 for a in cl if a['pnl'] > 0)}, net {sum(a['pnl'] for a in cl):+.2f}), {sum(1 for a in rows if a['status'] == 'open')} still open")
print(f"- engine score at open: 1.0 for {sum(1 for a in rows if a['engine_conf'] == 1.0)}, below 1.0 for {sum(1 for a in rows if a['engine_conf'] is not None and a['engine_conf'] < 1.0)}")
