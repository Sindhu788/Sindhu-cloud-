"""Master plan B5: turns the BT-RUN-v2 job output into docs/STRATEGY_V2_REPORT.md, a section in docs/BACKTEST_RESULTS.md and SVG
equity/drawdown charts in docs/strategy_v2/ (no plotting library is installed; the SVG is drawn directly).
Usage (any venv with numpy): python tools/benchmark_v2_report.py [--job D:\\sindhu_runtime\\bt_jobs\\BT-RUN-v2] [--write]"""
import argparse
import datetime as dt
import json
import os

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAY = 86_400_000
START = int(dt.datetime(2018, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
OOS = int(dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)


def load(job, name):
    return json.load(open(os.path.join(job, name + ".json"), encoding="utf-8"))


def svg_chart(series, title, path, log=True, drawdown=False):
    W, H, L, R, T, B = 900, 360, 60, 150, 30, 30
    colors = {"Donchian ensemble": "#2563eb", "Vol-scaled TSMOM": "#16a34a", "BTC buy & hold": "#f59e0b", "Equal-weight buy & hold": "#6b7280"}
    vals = []
    prepared = {}
    for name, eq in series.items():
        eq = np.asarray(eq, dtype=float)
        y = (eq / np.maximum.accumulate(eq) - 1) * 100 if drawdown else (np.log10(eq) if log else eq)
        prepared[name] = y
        vals.append(y[np.isfinite(y)])
    allv = np.concatenate(vals)
    lo, hi = float(np.min(allv)), float(np.max(allv))
    n = max(len(v) for v in prepared.values())
    sx = lambda i: L + (W - L - R) * i / (n - 1)
    sy = lambda v: T + (H - T - B) * (1 - (v - lo) / (hi - lo if hi > lo else 1))
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" font-family="system-ui,Segoe UI,Arial" font-size="12">',
             f'<rect width="{W}" height="{H}" fill="white"/>', f'<text x="{L}" y="18" font-size="14" font-weight="600">{title}</text>']
    oos_i = (OOS - START) // DAY
    parts.append(f'<line x1="{sx(oos_i):.1f}" y1="{T}" x2="{sx(oos_i):.1f}" y2="{H - B}" stroke="#999" stroke-dasharray="4 4"/>')
    parts.append(f'<text x="{sx(oos_i) + 4:.1f}" y="{T + 12}" fill="#666">out-of-sample from 2024-01-01</text>')
    for k in range(5):
        v = lo + (hi - lo) * k / 4
        label = f"{v:.0f}%" if drawdown else (f"${10 ** v:,.0f}" if log else f"{v:.0f}")
        parts.append(f'<line x1="{L}" y1="{sy(v):.1f}" x2="{W - R}" y2="{sy(v):.1f}" stroke="#eee"/><text x="4" y="{sy(v) + 4:.1f}" fill="#666">{label}</text>')
    for y in range(2018, 2027):
        i = (int(dt.datetime(y, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000) - START) // DAY
        if i < n:
            parts.append(f'<text x="{sx(i) - 14:.1f}" y="{H - 10}" fill="#666">{y}</text>')
    for k, (name, y) in enumerate(prepared.items()):
        step = max(1, len(y) // 900)
        pts = " ".join(f"{sx(i):.1f},{sy(v):.1f}" for i, v in list(enumerate(y))[::step] if np.isfinite(v))
        c = colors.get(name, "#000")
        parts.append(f'<polyline fill="none" stroke="{c}" stroke-width="1.6" points="{pts}"/>')
        parts.append(f'<rect x="{W - R + 10}" y="{T + 18 * k}" width="12" height="3" fill="{c}"/><text x="{W - R + 28}" y="{T + 18 * k + 5}">{name}</text>')
    parts.append("</svg>")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))


def fmt(m, k):
    v = m.get(k) if m else None
    if v is None:
        return "-"
    if isinstance(v, float) and (v != v):
        return "-"
    if v == float("inf"):
        return "inf"
    return f"{v:,.2f}" if isinstance(v, float) else str(v)


def build(job):
    v = json.load(open(os.path.join(job, "verdicts.json"), encoding="utf-8"))
    run1 = os.path.join(os.path.dirname(job), "BT-RUN", "verdicts.json")
    v1 = json.load(open(run1, encoding="utf-8")) if os.path.exists(run1) else {}
    names = {"donchian": "Donchian ensemble", "tsmom": "Vol-scaled TSMOM"}
    base = {s: load(job, f"{s}__base") for s in names}
    gross = {s: load(job, f"{s}__gross_costs0") for s in names}
    stress = {s: load(job, f"{s}__costs_x1_5") for s in names}
    btc, ew = load(job, "bench__btc_buy_hold"), load(job, "bench__equal_weight")
    os.makedirs(os.path.join(ROOT, "docs", "strategy_v2"), exist_ok=True)
    series = {names["donchian"]: base["donchian"]["equity"], names["tsmom"]: base["tsmom"]["equity"],
              "BTC buy & hold": btc["equity"], "Equal-weight buy & hold": ew["equity"]}
    svg_chart(series, "Equity, $100 start, after costs (log scale)", os.path.join(ROOT, "docs", "strategy_v2", "equity.svg"))
    svg_chart(series, "Drawdown from the previous peak (%)", os.path.join(ROOT, "docs", "strategy_v2", "drawdown.svg"), drawdown=True)

    keys = [("total_return_pct", "Total return %"), ("cagr_pct", "CAGR %"), ("sharpe", "Sharpe"), ("sortino", "Sortino"),
            ("max_drawdown_pct", "Max drawdown %"), ("profit_factor", "Profit factor (positions)"), ("positions", "Positions"),
            ("win_rate_pct", "Win rate %"), ("exposure_pct", "Exposure %"), ("t_stat", "t-stat (daily)")]
    L = []
    L.append("# STRATEGY V2 REPORT: two pre-registered daily trend strategies (master plan B5)\n")
    L.append(f"Generated {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC from `{job}` (run 2, see the pre-registration's Amendment 2). "
             "Rules, universe, costs and verdict criteria: docs/BENCHMARK_PREREGISTRATION_V2.md (committed 7388c1b before any data or result). "
             "Local backtest only: nothing was synced to Cloud, and nothing trades with these strategies.\n")
    L.append("## Verdicts\n")
    L.append("| Strategy | Verdict (run 2) | Run 1 verdict | Failed rule(s) | OOS p (block bootstrap) |")
    L.append("|---|---|---|---|---|")
    for s, nm in names.items():
        fails = [k for k, ok in v[s]["checks"].items() if not ok] or ["none"]
        L.append(f"| {nm} | **{v[s]['verdict']}** | {v1.get(s, {}).get('verdict', '-')} | {'; '.join(fails)} | {v[s]['oos_p']:.3f} |")
    L.append("\n**In plain words.**")
    L.append("- Both strategies made money after costs in-sample (2018–2023) and out-of-sample (2024 to Oct 2026).")
    L.append("- Both did so in 4 of 6 walk-forward years, and all 8 parameter neighbours of each stayed positive.")
    L.append("- Their out-of-sample Sharpe beat both buy-and-hold benchmarks, with much smaller drawdowns.")
    L.append("- But neither is statistically strong enough. Among 44 tested strategies (the 42 earlier ones plus these 2), a result this "
             "good can still be luck (p = 0.17 and 0.12; Benjamini–Hochberg can never accept a p above 0.05, whatever the rank).")
    L.append("- They also made LESS absolute money than simply holding BTC or an equal-weight basket out-of-sample: they sit in cash "
             "74–80 % of the time (exposure 26 % and 20 %).")
    L.append("- Verdict: **FRAGILE, no proven edge**. Not a candidate for live use; at most a forward-test candidate (owner decision).\n")
    L.append("## Results by period (after costs, $100 start; daily Sharpe annualised with √365)\n")
    for per, lab in (("IS", "In-sample 2018-01-01 → 2023-12-31"), ("OOS", "Out-of-sample 2024-01-01 → 2026-10-31")):
        L.append(f"### {lab}\n")
        L.append("| Metric | Donchian ensemble | Vol-scaled TSMOM | BTC buy & hold | Equal-weight buy & hold |")
        L.append("|---|---|---|---|---|")
        for k, lab2 in keys:
            L.append(f"| {lab2} | {fmt(base['donchian'][per], k)} | {fmt(base['tsmom'][per], k)} | {fmt(btc[per], k)} | {fmt(ew[per], k)} |")
        L.append("")
    L.append("### Walk-forward test years (total return %, Sharpe)\n")
    L.append("| Year | Donchian | TSMOM | BTC B&H | EW B&H |")
    L.append("|---|---|---|---|---|")
    for y in ("2021", "2022", "2023", "2024", "2025", "2026"):
        row = [f"{d['WF_' + y]['total_return_pct']:+.1f} ({d['WF_' + y]['sharpe']:.2f})" for d in (base["donchian"], base["tsmom"], btc, ew)]
        L.append(f"| {y}{' (Jan–Oct)' if y == '2026' else ''} | " + " | ".join(row) + " |")
    L.append("\n### Robustness\n")
    L.append("| Check | Donchian | TSMOM |")
    L.append("|---|---|---|")
    from data_platform import benchmark_v2 as bv
    for s in names:
        pass
    nb_d = dict(zip([l for l, _ in bv.neighbours("donchian")], v["donchian"]["neighbour_oos_returns_pct"]))
    nb_t = dict(zip([l for l, _ in bv.neighbours("tsmom")], v["tsmom"]["neighbour_oos_returns_pct"]))
    L.append(f"| Neighbours, OOS total return % | {', '.join(f'{k}: {x:+.1f}' for k, x in nb_d.items())} | {', '.join(f'{k}: {x:+.1f}' for k, x in nb_t.items())} |")
    L.append(f"| Pooled profit factor x1 / x1.5 costs | {v['donchian']['pooled_pf_x1']:.2f} / {v['donchian']['pooled_pf_x1_5']:.2f} | {v['tsmom']['pooled_pf_x1']:.2f} / {v['tsmom']['pooled_pf_x1_5']:.2f} |")
    L.append(f"| OOS total return at 1.5x costs | {stress['donchian']['OOS']['total_return_pct']:+.1f} % | {stress['tsmom']['OOS']['total_return_pct']:+.1f} % |")
    L.append(f"| Cost drag (CAGR gross − net), IS / OOS | {gross['donchian']['IS']['cagr_pct'] - base['donchian']['IS']['cagr_pct']:.2f} / {gross['donchian']['OOS']['cagr_pct'] - base['donchian']['OOS']['cagr_pct']:.2f} pts | {gross['tsmom']['IS']['cagr_pct'] - base['tsmom']['IS']['cagr_pct']:.2f} / {gross['tsmom']['OOS']['cagr_pct'] - base['tsmom']['OOS']['cagr_pct']:.2f} pts |")
    L.append(f"| Mean net return per position, 95 % bootstrap CI (IS+OOS) | {base['donchian']['position_return_ci95_pct']} % | {base['tsmom']['position_return_ci95_pct']} % |")
    L.append(f"| Positions IS+OOS / OOS | {v['donchian']['positions_full']} / {v['donchian']['positions_oos']} | {v['tsmom']['positions_full']} / {v['tsmom']['positions_oos']} |")
    L.append(f"| Turnover (x starting capital per year, approximate) | {base['donchian']['turnover_per_year_x']} | {base['tsmom']['turnover_per_year_x']} |")
    L.append("\n![equity](strategy_v2/equity.svg)\n\n![drawdown](strategy_v2/drawdown.svg)\n")
    L.append("## Limitations (read before believing any number)")
    L.append("- **Survivorship bias:** the universe is today's top coins that already existed in 2023. Coins that died are missing, so the results are optimistic.")
    L.append("- **Short history, one regime family:** crypto spot from 2018 has only a few bull/bear cycles. 2022 was negative for both strategies.")
    L.append("- **Multiple testing:** 44 strategies have now been tried on this market; the FDR rule is what failed here.")
    L.append("- **Small account:** fractional sizes are assumed. At $100 the 1/20 weights hit Binance's $5 minimum notional, so real fills would differ.")
    L.append("- **Not perfectly untouched OOS:** Sep–Oct 2026 was looked at earlier for other strategies.")
    L.append("- **Run 1 bug:** the first run mis-valued the benchmarks on the 8 Feb 2018 outage day; fixed and re-run (Amendment 2). Strategy numbers did not change.")
    L.append("- Charts are SVG, not PNG: no plotting library is installed and none was added.\n")
    L.append("## What to try next (ranked, each needs its own pre-registration)")
    months = 34.0                                   # 2024-01-01 .. 2026-10-31
    rate_d, rate_t = v["donchian"]["positions_oos"] / months, v["tsmom"]["positions_oos"] / months
    L.append(f"1. Put both into the **forward test** as paper-only candidates (owner decision). At their out-of-sample rates "
             f"({rate_d:.1f} and {rate_t:.1f} new positions a month over 20 coins), reaching the protocol's 100 positions takes about "
             f"{100 / rate_d:.0f} and {100 / rate_t:.0f} months, so a verdict on 5 Jan 2027 would be INSUFFICIENT_DATA for both.")
    L.append("2. A **combined** trend portfolio (the two signals averaged): may lower variance, but it is a NEW test and counts as #45.")
    L.append("3. A survivorship-free universe (top-20 re-ranked each year from that year's data) to measure how much of the result is survivorship.")
    return "\n".join(L) + "\n", v


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ROOT)
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", default=r"D:\sindhu_runtime\bt_jobs\BT-RUN-v2")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    text, v = build(a.job)
    print(text)
    if a.write:
        with open(os.path.join(ROOT, "docs", "STRATEGY_V2_REPORT.md"), "w", encoding="utf-8") as f:
            f.write(text)
        br = os.path.join(ROOT, "docs", "BACKTEST_RESULTS.md")
        if "## V2 benchmark strategies (master plan Part B" in open(br, encoding="utf-8").read():
            sys.exit(0)                                  # idempotent: the summary section is written once
        with open(br, "a", encoding="utf-8") as f:
            f.write(f"\n## V2 benchmark strategies (master plan Part B, {dt.date.today()})\n"
                    f"Donchian trend ensemble 1d: **{v['donchian']['verdict']}**; vol-scaled TSMOM 1d: **{v['tsmom']['verdict']}**. "
                    "Both positive after costs IS and OOS, robust to neighbours and 1.5x costs, but fail the FDR rule over 44 tests "
                    "and earn less than buy-and-hold in absolute terms. Full report: docs/STRATEGY_V2_REPORT.md.\n")
