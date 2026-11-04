"""Read-only strategy forensics on the closed paper trades in the Cloud database (Neon). Prints Markdown. Nothing is changed.
Usage: python scripts/strategy_forensics.py [min_trades=25]
Data window = whatever closed trades exist (29 Aug - 4 Nov 2026; almost all from 29 Aug - 16 Sep)."""
import collections
import datetime as dt
import json
import sys

import numpy as np
import psycopg

sys.stdout.reconfigure(encoding="utf-8")
MIN_N = int(sys.argv[1]) if len(sys.argv) > 1 else 25
url = json.load(open("D:/sindhu/data/config/neon_runtime_connection.json"))["database_url"]
with psycopg.connect(url, connect_timeout=30, options="-c default_transaction_read_only=on") as c:
    cur = c.cursor()
    cur.execute("""SELECT p.strategy_id, coalesce(p.strategy_name,''), p.symbol, p.direction, p.entry_time, p.exit_time, p.pnl, p.risk_amount,
                          coalesce(p.market_state,'?'), coalesce(p.session,'?'), coalesce(p.timeframe,'?'), coalesce(g.group_key,'-'), p.exit_reason
                   FROM paper_positions p LEFT JOIN paper_strategy_groups g ON g.strategy_id = p.strategy_id
                   WHERE p.status != 'open' AND p.pnl IS NOT NULL AND p.entry_time IS NOT NULL ORDER BY p.entry_time""")
    rows = cur.fetchall()

T = [dict(sid=r[0], name=r[1], sym=r[2], side=r[3], et=float(r[4]) / 1000, xt=float(r[5] or r[4]) / 1000, pnl=float(r[6]), risk=float(r[7] or 0) or None,
          state=r[8], session=r[9], tf=r[10], grp=r[11], why=r[12]) for r in rows]
for t in T:
    t["hour"] = dt.datetime.fromtimestamp(t["et"], dt.timezone.utc).hour
    t["month"] = dt.datetime.fromtimestamp(t["et"], dt.timezone.utc).strftime("%Y-%m")
    t["r"] = t["pnl"] / t["risk"] if t["risk"] else None


def stats(ts):
    n = len(ts)
    if not n:
        return None
    p = np.array([t["pnl"] for t in ts]); w = p[p > 0].sum(); l = -p[p < 0].sum()
    eq = np.cumsum(p); dd = float((np.maximum.accumulate(eq) - eq).max()) if n else 0.0
    rs = [t["r"] for t in ts if t["r"] is not None]
    return dict(n=n, win=100 * float((p > 0).mean()), pf=(w / l if l > 0 else float("inf")), net=float(p.sum()), avg_r=(float(np.mean(rs)) if rs else float("nan")), dd=dd)


def fmt(s):
    pf = "inf" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
    return f"{s['n']} | {s['win']:.1f} | {pf} | {s['net']:+.2f} | {s['avg_r']:+.2f} | {s['dd']:.2f}"


print(f"Closed trades with P&L: {len(T)}; first {dt.datetime.fromtimestamp(T[0]['et'], dt.timezone.utc):%Y-%m-%d}, last {dt.datetime.fromtimestamp(T[-1]['et'], dt.timezone.utc):%Y-%m-%d}")
print("By month of entry: " + ", ".join(f"{m}: {n}" for m, n in sorted(collections.Counter(t['month'] for t in T).items())))
print("\n## Overall splits (trades | win % | PF | net | avg R | max DD)")
print("| Split | Value | n | win % | PF | net | avg R | max DD |\n|---|---|---|---|---|---|---|---|")
for key in ("grp", "side", "state", "session", "tf"):
    for v, ts in sorted(collections.defaultdict(list, {}).items()):
        pass
    d = collections.defaultdict(list)
    for t in T:
        d[t[key]].append(t)
    for v, ts in sorted(d.items(), key=lambda kv: -len(kv[1])):
        print(f"| {key} | {v} | {fmt(stats(ts))} |")
d = collections.defaultdict(list)
for t in T:
    d[t["hour"] // 6].append(t)
for v, ts in sorted(d.items()):
    print(f"| UTC hours | {v * 6:02d}-{v * 6 + 5:02d} | {fmt(stats(ts))} |")

print(f"\n## Per strategy with at least {MIN_N} closed trades")
print("| Strategy | Group | n | win % | PF | net | avg R | max DD | long n / net | short n / net | top coin share | worst hour block (n,net) | Trust |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|")
by = collections.defaultdict(list)
for t in T:
    by[t["sid"]].append(t)
rows_out = []
for sid, ts in by.items():
    if len(ts) < MIN_N:
        continue
    s = stats(ts)
    L = [t for t in ts if t["side"] == "long"]; S = [t for t in ts if t["side"] == "short"]
    cc = collections.Counter(t["sym"] for t in ts)
    hb = collections.defaultdict(list)
    for t in ts:
        hb[t["hour"] // 6].append(t)
    worst = min(((k, sum(x["pnl"] for x in v), len(v)) for k, v in hb.items()), key=lambda z: z[1])
    trust = "ok" if len(ts) >= 100 else ("small" if len(ts) >= 50 else "too small for firm conclusions")
    rows_out.append((s["net"], f"| {ts[0]['name'][:44]} | {ts[0]['grp']} | {fmt(s)} | {len(L)} / {sum(x['pnl'] for x in L):+.2f} | {len(S)} / {sum(x['pnl'] for x in S):+.2f} | "
                                  f"{100 * cc.most_common(1)[0][1] / len(ts):.0f} % ({cc.most_common(1)[0][0].split('/')[0]}) | {worst[0] * 6:02d}-{worst[0] * 6 + 5:02d} ({worst[2]}, {worst[1]:+.2f}) | {trust} |"))
for _, line in sorted(rows_out, reverse=True):
    print(line)
print(f"\n{len(rows_out)} strategies have >= {MIN_N} trades; {len(by) - len(rows_out)} have fewer (no conclusion possible).")

print("\n## Regime (market_state at entry) per strategy, strategies with >= 50 trades: net P&L in each state (n)")
states = sorted({t["state"] for t in T})
print("| Strategy | " + " | ".join(states) + " |\n|---|" + "---|" * len(states))
for sid, ts in sorted(by.items(), key=lambda kv: -len(kv[1])):
    if len(ts) < 50:
        continue
    cells = []
    for st in states:
        x = [t for t in ts if t["state"] == st]
        cells.append(f"{sum(t['pnl'] for t in x):+.1f} ({len(x)})" if x else "-")
    print(f"| {ts[0]['name'][:40]} | " + " | ".join(cells) + " |")

print("\n## Redundancy: do strategies fire on the same coin, side and 15-minute slot?")
slot = lambda t: (t["sym"], t["side"], int(t["et"] // 900))
ev = collections.defaultdict(set)
for t in T:
    ev[slot(t)].add(t["sid"])
multi = sum(1 for v in ev.values() if len(v) > 1)
print(f"Distinct (coin, side, 15-min slot) events: {len(ev)} from {len(T)} trades -> {len(T) / len(ev):.2f} trades per independent event; events where >= 2 strategies fired together: {multi} ({100 * multi / len(ev):.1f} %).")
# effective independent bets using pnl correlation of strategies on shared slots
sids = [s for s, ts in by.items() if len(ts) >= MIN_N]
sl = {s: {slot(t): t["pnl"] for t in by[s]} for s in sids}
pairs = []
for i in range(len(sids)):
    for j in range(i + 1, len(sids)):
        a, b = sl[sids[i]], sl[sids[j]]
        inter = set(a) & set(b)
        if len(inter) >= 5:
            jac = len(inter) / len(set(a) | set(b))
            pairs.append((jac, len(inter), by[sids[i]][0]["name"][:34], by[sids[j]][0]["name"][:34]))
print("| Overlap (Jaccard of events) | shared events | Strategy A | Strategy B |\n|---|---|---|---|")
for jac, n, a, b in sorted(pairs, reverse=True)[:12]:
    print(f"| {jac:.2f} | {n} | {a} | {b} |")
# group strategies with overlap >= 0.3 greedily -> effective number of independent strategies
parent = {s: s for s in sids}
def find(x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]; x = parent[x]
    return x
for i in range(len(sids)):
    for j in range(i + 1, len(sids)):
        a, b = sl[sids[i]], sl[sids[j]]
        inter = set(a) & set(b)
        if inter and len(inter) / len(set(a) | set(b)) >= 0.3:
            parent[find(sids[i])] = find(sids[j])
clusters = collections.Counter(find(s) for s in sids)
print(f"\nStrategies with >= {MIN_N} trades: {len(sids)}; clusters when overlap >= 0.30: {len(clusters)} (largest cluster {max(clusters.values()) if clusters else 0}).")
