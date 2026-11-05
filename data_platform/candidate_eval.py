"""Candidate strategy evaluation in a LOCAL SANDBOX (Day 6 Step 19).
    python -m data_platform.candidate_eval --library-dir <folder with <id>/meta.json + versions/> --strategy-id <id> [--coins 50] [--workers 2]
                                           [--sims 500] [--claim my_claim.md] [--out-root D:\\sindhu_data\\candidates]
Pipeline: scrub credentials from the environment, lock the network, copy the candidate into its own folder, run the unchanged backtest protocol on the
development window (never the sealed holdout, never the forward window), score it with the corrected metrics, add bootstrap intervals, the random-entry
null model and the baselines, then write `DOSSIER.md` (idea, rules, timeframe, costs, walk-forward, comparison, fee sensitivity, label, one-page verdict).
Nothing is synced to Cloud, nothing is sent to Telegram: the process has no credentials and cannot open outgoing connections (data_platform/sandbox.py).
To bring in a NEW strategy: run the normal import with SINDHU_DATA_DIR and SINDHU_STRATEGY_LIBRARY_DIR pointing at scratch folders, then pass that library here."""
import argparse
import datetime as dt
import json
import os
import shutil
import sys

from data_platform import sandbox


def verdict_lines(res, rig, label):
    lines = []
    n = res.get("trades", 0)
    lines.append(f"**Label: {label}.** {n:,} positions on {res.get('coins_run', 0)} coins; profit factor after costs {res.get('pf_x1', 0):.2f} "
                 f"(x1.5 costs {res.get('pf_x1_5', 0):.2f}, x2 {res.get('pf_x2', 0):.2f}, before costs {res.get('pf_gross', 0):.2f}).")
    if rig.get("pf_ci"):
        lines.append(f"95 % interval of the profit factor (days as clusters): {rig['pf_ci'][0]:.2f} to {rig['pf_ci'][1]:.2f}. "
                     f"Random-entry null model: strategy {rig['obs_mean_net_pct']:+.3f} % per position vs random entries {rig['null_mean_pct']:+.3f} % (p = {rig['null_p']:.3f}). "
                     f"Baselines per trade: SMA-4h {rig['sma4h_mean_net_pct']:+.3f} %, RSI-1h {rig['rsi1h_mean_net_pct']:+.3f} %.")
    if label == "ROBUST":
        lines.append("It passes every backtest check. That is NOT yet a promotion: the pre-registered forward test (60 days, 100 positions) and the owner's approval are still required (docs/PIPELINE.md).")
    elif label == "INSUFFICIENT_DATA":
        lines.append(f"Too few trades to judge ({res.get('reason', '')}). Do not conclude anything either way.")
    else:
        lines.append("It does not pass: " + (res.get("reason") or "robustness rules failed") + ". Do not promote.")
    return lines


def build_dossier(out_dir, sid, claim_text, res, rig, label, cfg_summary, removed_names, elapsed_min):
    L = [f"# Candidate dossier: {cfg_summary.get('name', sid)} ({sid})", "",
         f"Generated {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC in {elapsed_min:.1f} min. Sandbox: credentials removed ({len(removed_names)} environment variables, names not listed), "
         "network locked, no Cloud sync, no Telegram.", "",
         "## 1. Owner's claim", claim_text.strip() if claim_text else "NOT FILLED (docs/templates/CANDIDATE_CLAIM_TEMPLATE.md)", "",
         "## 2. One-page verdict", *verdict_lines(res, rig, label), "",
         "## 3. Rules and timeframe", f"- Entry timeframe: {cfg_summary.get('entry_tf')}; all timeframes: {cfg_summary.get('timeframes')}",
         f"- Risk per trade: {cfg_summary.get('risk_pct')} %", "- Rules (from the strategy file; not edited by the evaluation): see `strategy_library/` in this folder", "",
         "## 4. Costs", "Binance spot taker commission 0.10 % per side, spread and slippage by liquidity tier plus volatility (data_platform/cost_model.py). Sensitivity x1 / x1.5 / x2 by exact re-pricing.", "",
         "## 5. Results (development window, corrected position-level metrics)",
         "| Measure | Value |", "|---|---|",
         f"| Positions | {res.get('trades')} |", f"| Win rate | {res.get('win_rate')} % |", f"| Profit factor x1 / x1.5 / x2 / gross | {res.get('pf_x1', 0):.2f} / {res.get('pf_x1_5', 0):.2f} / {res.get('pf_x2', 0):.2f} / {res.get('pf_gross', 0):.2f} |",
         f"| Net result (money, 1,000 account, 10 % size) | {res.get('net_total')} |", f"| Max drawdown (money) | {res.get('max_drawdown')} |",
         f"| Average R / t-statistic per position (optimistic, see protocol) | {res.get('avg_R')} / {res.get('t_stat')} |",
         f"| Long / short (positions, PF) | {res.get('long_n')} / {res.get('long_pf')} ; {res.get('short_n')} / {res.get('short_pf')} |",
         f"| Walk-forward windows with PF >= 1.1 | {res.get('windows_pf_ok')} of {res.get('windows_qualifying')} qualifying (8 windows) |",
         f"| Coins with PF >= 1.1 | {res.get('coins_pf_ok')} of {res.get('coins_qualifying')} qualifying |", f"| Per window (positions, PF) | {res.get('windows')} |",
         f"| Hour blocks UTC (positions, PF) | {res.get('hour_blocks')} |", "",
         "## 6. Comparison with luck and with simple rules", "| Measure | Value |", "|---|---|"]
    for k in ("obs_mean_net_pct", "null_mean_pct", "null_p95_pct", "null_p", "fdr_pass", "sma4h_mean_net_pct", "sma4h_trades", "rsi1h_mean_net_pct", "rsi1h_trades", "buy_hold_mean_return_pct", "pf_ci", "mean_money_ci"):
        L.append(f"| {k} | {rig.get(k)} |")
    L += ["", "## 7. What this dossier cannot tell you", "Only 10 months of one market regime; spot costs only; fills at the signal-bar close; no market impact. A pass is a reason to run the forward test, never a reason to trade."]
    with open(os.path.join(out_dir, "DOSSIER.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def main(argv=None):
    removed = sandbox.scrub_environment()          # BEFORE any other project module is imported
    sandbox.lock_network()
    ap = argparse.ArgumentParser()
    ap.add_argument("--library-dir", required=True)
    ap.add_argument("--strategy-id", required=True)
    ap.add_argument("--coins", type=int, default=50)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--sims", type=int, default=500)
    ap.add_argument("--claim", default=None)
    ap.add_argument("--out-root", default=os.path.join(os.environ.get("SINDHU_DATA_ROOT", r"D:\sindhu_data"), "candidates"))
    a = ap.parse_args(argv)
    import time
    t0 = time.time()
    out = os.path.join(a.out_root, f"{a.strategy_id}_{dt.datetime.now(dt.timezone.utc):%Y%m%d_%H%M}")
    lib = os.path.join(out, "strategy_library")
    os.makedirs(lib, exist_ok=True)
    shutil.copytree(os.path.join(a.library_dir, a.strategy_id), os.path.join(lib, a.strategy_id))      # a COPY: the source library is never touched
    os.environ["SINDHU_STRATEGY_LIBRARY_DIR"] = lib
    from backtest_engine import strategy_library
    cfg = strategy_library.load(a.strategy_id)
    summary = {"name": cfg.name, "entry_tf": cfg.timeframes.get("entry"), "timeframes": dict(cfg.timeframes), "risk_pct": cfg.risk_pct}
    with open(os.path.join(out, "strategies_42.json"), "w", encoding="utf-8") as f:
        json.dump([{"id": a.strategy_id, "name": cfg.name, "group": "candidate", "entry_tf": summary["entry_tf"]}], f)
    from data_platform import protocol_analyze, protocol_rigor, protocol_run
    protocol_run.main(["--strategies", a.strategy_id, "--coins", str(a.coins), "--workers", str(a.workers), "--out", out])
    protocol_analyze.main([out])
    protocol_rigor.main(["--out", out, "--only", a.strategy_id, "--sims", str(a.sims)])
    res = {r["strategy_id"]: r for r in json.load(open(os.path.join(out, "protocol_results.json")))["results"]}[a.strategy_id]
    rig = json.load(open(os.path.join(out, "protocol_rigor.json")))["results"].get(a.strategy_id, {})
    label = protocol_rigor.final_label(res["label"], rig)
    claim = open(a.claim, encoding="utf-8").read() if a.claim else ""
    build_dossier(out, a.strategy_id, claim, res, rig, label, summary, removed, (time.time() - t0) / 60)
    print("DOSSIER:", os.path.join(out, "DOSSIER.md"), "| label", label)


if __name__ == "__main__":
    main()
