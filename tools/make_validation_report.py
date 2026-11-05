"""Day 6 Steps 8-11: turns protocol_results.json + protocol_rigor.json into the report sections (markdown on stdout, or appended to docs with --write).
Read-only on the results; reads strategy groups from the local database (read-only). Usage (after protocol_run, protocol_analyze, protocol_rigor):
  python tools/make_validation_report.py [--write] [--scan-seconds 865]"""
import argparse
import collections
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data_platform import protocol_rigor        # noqa: E402

EXP = os.path.join(os.environ.get("SINDHU_DATA_ROOT", r"D:\sindhu_data"), "experiments")
TF_MIN = {"1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "2h": 120, "4h": 240, "6h": 360, "8h": 480, "12h": 720, "1d": 1440, "1w": 10080}
SLOW = {"4h", "6h", "8h", "12h", "1d", "1w"}


def fmt(x, d=2):
    return "-" if x is None else (f"{x:.{d}f}" if isinstance(x, (int, float)) else str(x))


def load():
    res = {r["strategy_id"]: r for r in json.load(open(os.path.join(EXP, "protocol_results.json")))["results"]}
    rig = json.load(open(os.path.join(EXP, "protocol_rigor.json")))["results"]
    return res, rig


def groups():
    try:
        c = sqlite3.connect("file:D:/sindhu/data/database/sindhu.db?mode=ro", uri=True, timeout=10)
        return dict(c.execute("select strategy_id, group_key from paper_strategy_groups").fetchall())
    except Exception:
        return {}


def insufficient_reason(r):
    n = r["trades"]
    if n == 0:
        return "no trades at all"
    if n < protocol_rigor.protocol_analyze.MIN_TOTAL_TRADES:
        return ("timeframe problem: slow timeframe, few signals in 10 months" if r.get("entry_tf") in SLOW else f"too few trades ({n} < 300)")
    if r.get("windows_qualifying", 0) < protocol_rigor.protocol_analyze.MIN_WINDOWS:
        return f"trades bunched in too few windows ({r.get('windows_qualifying', 0)} of 8 with >= 30)"
    return "other"


def section8(res, rig, labels):
    L = ["## Day 6: corrected validation of the 42 enabled strategies (Step 8)", "",
         "Unit = position, corrected metrics (docs/BACKTEST_PROTOCOL.md section 10). Coins: up to 50 (coins with no data in the window are skipped, see the coin column). Development window "
         "1 Nov 2025 - 31 Aug 2026, 8 walk-forward windows scored by entry time, costs x1 with exact x1.5 / x2 re-pricing. No parameter changed; the holdout and the forward window were not read.", "",
         "| Label | Strategy | TF | Coins | Positions | Win % | PF x1 [95 % CI] | PF x1.5 | PF x2 | Expectancy ($) | Avg R | Max DD ($) | Windows ok | Coins ok | Long n / PF | Short n / PF |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    order = {"ROBUST": 0, "FRAGILE": 1, "FAILED": 2, "INSUFFICIENT_DATA": 3}
    for sid, r in sorted(res.items(), key=lambda kv: (order[labels[kv[0]]], -(kv[1].get("pf_x1") or 0))):
        g = rig.get(sid, {})
        ci = g.get("pf_ci")
        L.append(f"| {labels[sid]} | {r.get('name')} | {r.get('entry_tf')} | {r.get('coins_run')} | {r['trades']} | {fmt(r.get('win_rate'), 1)} | {fmt(r.get('pf_x1'))} "
                 f"[{fmt(ci[0]) if ci else '-'}-{fmt(ci[1]) if ci else '-'}] | {fmt(r.get('pf_x1_5'))} | {fmt(r.get('pf_x2'))} | {fmt(r.get('expectancy'), 3)} | {fmt(r.get('avg_R'), 3)} | "
                 f"{fmt(r.get('max_drawdown'), 0)} | {r.get('windows_pf_ok', 0)}/{r.get('windows_qualifying', 0)} | {r.get('coins_pf_ok', 0)}/{r.get('coins_qualifying', 0)} | "
                 f"{r.get('long_n', '-')} / {fmt(r.get('long_pf'))} | {r.get('short_n', '-')} / {fmt(r.get('short_pf'))} |")
    L += ["", "**Hour-of-day split (UTC, 6-hour blocks; positions, PF) for the strategies with >= 300 positions:**", "",
          "| Strategy | 00-05 | 06-11 | 12-17 | 18-23 |", "|---|---|---|---|---|"]
    for sid, r in sorted(res.items(), key=lambda kv: -kv[1]["trades"]):
        if r["trades"] >= 300 and r.get("hour_blocks"):
            hb = r["hour_blocks"]
            L.append(f"| {r.get('name')} | " + " | ".join(f"{hb[k][0]} / {fmt(hb[k][1])}" for k in ("00-05", "06-11", "12-17", "18-23")) + " |")
    ins = [r for r in res.values() if labels[r["strategy_id"]] == "INSUFFICIENT_DATA"]
    L += ["", f"**Why {len(ins)} strategies are INSUFFICIENT_DATA:**", "", "| Strategy | TF | Positions | Reason |", "|---|---|---|---|"]
    for r in sorted(ins, key=lambda r: r["trades"]):
        L.append(f"| {r.get('name')} | {r.get('entry_tf')} | {r['trades']} | {insufficient_reason(r)} |")
    return L


def section9(res, rig, labels):
    L = ["", "## Day 6: comparison with luck and with simple baselines (Step 9)", "",
         "Net return per position as % of notional, same costs. Null = random entries with the same side mix, holding times and costs (500 simulated books). p = share of simulated books at least as good (smaller = stronger evidence). FDR = survives Benjamini-Hochberg at 5 % across all strategies.", "",
         "| Strategy | TF | Positions | Strategy % | Random-entry % (95th pct) | p | FDR | SMA-4h % | RSI-1h % | Beats luck | Beats both baselines |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    beat_null = beat_base = 0
    for sid, g in sorted(rig.items(), key=lambda kv: -kv[1].get("obs_mean_net_pct", -9)):
        if "null_p" not in g:
            continue
        luck = g["null_p"] < 0.05 and g.get("fdr_pass")
        base = g["obs_mean_net_pct"] > max(g["sma4h_mean_net_pct"], g["rsi1h_mean_net_pct"])
        beat_null += bool(luck); beat_base += bool(base)
        L.append(f"| {res[sid].get('name')} | {res[sid].get('entry_tf')} | {g['positions']} | {g['obs_mean_net_pct']:+.3f} | {g['null_mean_pct']:+.3f} ({g['null_p95_pct']:+.3f}) | {g['null_p']:.3f} | "
                 f"{'yes' if g.get('fdr_pass') else 'no'} | {g['sma4h_mean_net_pct']:+.3f} | {g['rsi1h_mean_net_pct']:+.3f} | {'YES' if luck else 'no'} | {'yes' if base else 'no'} |")
    bh = [g["buy_hold_mean_return_pct"] for g in rig.values() if "buy_hold_mean_return_pct" in g]
    L += ["", f"**Result: {beat_null} of {len(rig)} strategies beat random entries significantly (FDR-controlled); {beat_base} of {len(rig)} beat both trade-based baselines on mean return per position.** "
          + ("No strategy beats luck." if beat_null == 0 else "See the YES rows; each still has to pass the PF-interval and window/coin rules."),
          f"Buy-and-hold context: the average coin lost about {abs(sum(bh) / len(bh)):.0f} % over the window (mean of per-strategy coin sets, one round trip of costs included)." if bh else ""]
    return L


def section10(res, rig, labels, scan_s):
    by = collections.defaultdict(list)
    for r in res.values():
        by[r.get("entry_tf")].append(r)
    L = ["", "## Day 6: results by timeframe and live eligibility (Step 10)", "",
         f"Live rule used here (stated, measured input): the Cloud scan of 10 coins took **{scan_s} s ({scan_s / 60:.1f} min)** on commit 8185853 (Step 12/14 may lower it). A strategy on timeframe T is evaluated once per scan, so a new candle can wait up to one scan before it is seen, and a signal older than the 15-minute freshness window is rejected. "
         "So: T <= 5m cannot be served (a candle every 1-5 min vs one look per ~14 min); 15m is borderline (the scan is almost one full candle long); T >= 30m can be served.", "",
         "| Entry TF | Strategies | Positions | Strategies with PF x1 > 1 | Best PF x1 | Median PF x1 | ROBUST | FAILED | INSUFFICIENT | Can Cloud serve it live today? |", "|---|---|---|---|---|---|---|---|---|---|"]
    for tf in sorted(by, key=lambda t: TF_MIN.get(t, 10 ** 6)):
        rs = by[tf]
        pfs = sorted(r.get("pf_x1") or 0 for r in rs)
        mins = TF_MIN.get(tf, 0)
        live = "no (scan too slow for the candle period)" if mins <= 5 else ("borderline" if mins <= 15 else "yes")
        c = collections.Counter(labels[r["strategy_id"]] for r in rs)
        L.append(f"| {tf} | {len(rs)} | {sum(r['trades'] for r in rs)} | {sum(1 for p in pfs if p > 1)} | {pfs[-1]:.2f} | {pfs[len(pfs) // 2]:.2f} | {c.get('ROBUST', 0)} | {c.get('FAILED', 0)} | {c.get('INSUFFICIENT_DATA', 0)} | {live} |")
    robust = [r for r in res.values() if labels[r["strategy_id"]] == "ROBUST"]
    L += ["", "**Which strategies could be live today?** " + (
        "None is validated, so none should be promoted. Servable by timeframe (30m and slower): " + ", ".join(sorted({r['name'] for r in res.values() if TF_MIN.get(r.get('entry_tf'), 0) >= 30})[:12]) + " ... (see table); but servable is not the same as good."
        if not robust else "ROBUST and servable: " + ", ".join(r["name"] for r in robust if TF_MIN.get(r.get("entry_tf"), 0) >= 30)),
        f"Count on 1m-5m (research-only candidates for `SINDHU_RESEARCH_ONLY_TIMEFRAMES`): {sum(len(v) for k, v in by.items() if TF_MIN.get(k, 99) <= 5)} of {len(res)} strategies."]
    return L


def section11(res, rig, labels):
    gm = groups()
    L = ["", "## Day 6: shortlist - recommendation only, nothing applied (Step 11)", "",
         "Rules: **KEEP** = label ROBUST. **WATCH** = INSUFFICIENT_DATA with PF x1 > 1 (not enough trades to say anything, do not trust the number) or FRAGILE. **PAUSE** = FAILED with the upper end of the 95 % PF interval below 1 (a loss that is statistically clear after costs). "
         "FAILED strategies whose interval still touches 1 stay in the 'FAILED, not yet clear-cut' list. Groups below are from the LOCAL database copy (last assigned 16 Sep 2026); the Cloud groups may differ: NOT VERIFIED.", ""]
    keep, watch, pause, other = [], [], [], []
    for sid, r in res.items():
        g = rig.get(sid, {})
        lab = labels[sid]
        hi = (g.get("pf_ci") or [None, None])[1]
        if lab == "ROBUST":
            keep.append(r)
        elif lab == "FRAGILE" or (lab == "INSUFFICIENT_DATA" and (r.get("pf_x1") or 0) > 1):
            watch.append(r)
        elif lab == "FAILED" and hi is not None and hi < 1.0:
            pause.append(r)
        else:
            other.append(r)
    pub = lambda rs: [r for r in rs if gm.get(r["strategy_id"]) in ("profitable", "challenge")]
    for title, rs in (("KEEP", keep), ("WATCH", watch), ("PAUSE (clear loss after costs)", pause), ("FAILED or INSUFFICIENT, not yet clear-cut (no action recommended beyond watching)", other)):
        L += [f"**{title}: {len(rs)}**", "", "| Strategy | TF | Group (local copy) | Positions | PF x1 [95 % CI] | Label |", "|---|---|---|---|---|---|"]
        for r in sorted(rs, key=lambda r: -(r.get("pf_x1") or 0)):
            ci = rig.get(r["strategy_id"], {}).get("pf_ci")
            L.append(f"| {r.get('name')} | {r.get('entry_tf')} | {gm.get(r['strategy_id'], '?')} | {r['trades']} | {fmt(r.get('pf_x1'))} [{fmt(ci[0]) if ci else '-'}-{fmt(ci[1]) if ci else '-'}] | {labels[r['strategy_id']]} |")
        L.append("")
    L += [f"**Expected effect on public signals:** only strategies in the Profitable or Challenge group can send Telegram signals (the Losing group sends none). Of the {len(pause)} PAUSE strategies, {len(pub(pause))} are in those groups (local copy): "
          + (", ".join(r['name'] for r in pub(pause)) or "none") + ". Pausing them would remove their signals; strategies in the Losing group change nothing publicly. "
          f"Of the {len(res)} strategies, {len(pub(res.values()))} are in the public groups (local copy).",
          "Nothing was paused or changed. The decision belongs to the owner (docs/OWNER_DECISIONS.md)."]
    return L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--scan-seconds", type=int, default=865)
    a = ap.parse_args()
    res, rig = load()
    labels = {sid: protocol_rigor.final_label(r["label"], rig.get(sid, {})) for sid, r in res.items()}
    parts = {"forensics": section8(res, rig, labels) + section9(res, rig, labels) + section10(res, rig, labels, a.scan_seconds), "decisions": section11(res, rig, labels)}
    if a.write:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for fn, key in (("STRATEGY_FORENSICS.md", "forensics"), ("OWNER_DECISIONS.md", "decisions")):
            with open(os.path.join(root, "docs", fn), "a", encoding="utf-8") as f:
                f.write("\n\n" + "\n".join(parts[key]) + "\n")
        print("appended to docs/STRATEGY_FORENSICS.md and docs/OWNER_DECISIONS.md")
    else:
        print("\n".join(parts["forensics"] + parts["decisions"]))
    print("labels:", dict(collections.Counter(labels.values())), file=sys.stderr)


if __name__ == "__main__":
    main()
