"""Item 2 (null take-profit engine bug, Master 15-Item task) verification
reruns. Runs a fixed list of strategy_ids through the same run_mtf_batch
pipeline used by the original New Batch 5 work, one strategy at a time
(not multiprocessed across strategies, to respect the tight local RAM/CPU
headroom flagged for this task -- each individual run_mtf_batch call still
uses multiprocessing internally across the 50 coins, same as before).

Usage: python scripts/_tmp_item2_rerun.py <set> <label>
  <set>: "laxman_dmc" (5 pre-existing affected variants) or "new_batch" (11
         affected New Batch 5 variants)
  <label>: free-text tag for the output filename, e.g. "pre_fix" / "post_fix"
           -- this script does not touch engine code itself; toggle the fix
           with git stash/pop around invocations of this script.
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


LAXMAN_DMC_IDS = {
    "laxman_base_rr3": "1f43468bb6af",
    "laxman_fixed12_rr2": "62698d8e936f",
    "laxman_strict_rr3": "8e56262e2b75",
    "laxman_medium_rr3": "b6bf0c760e89",
    "dmc_confirmation_fixed12_rr2": "6da11cec0f73",
}

NEW_BATCH_IDS = {
    "s1_loose": "96f7cb9100f0",
    "s1_strict": "594c16205e7f",
    "s4_fixed_2": "5a26c66ffa42",
    "s4_fixed_3": "54c9f3b67aa6",
    "s5_fixed_2": "edb442d731aa",
    "s7_loose": "2f6ff7755c8f",
    "s7_strict": "eba4cc77ee31",
}

# Strategy 9's 4 "indicator" exit-mode variant ids are read from the
# checkpoint file the original builder wrote (data/checkpoints/_strategy9_ids.json)
# rather than hardcoded here, since their ids weren't in this task's own notes.


def _load_strategy9_indicator_ids():
    path = os.path.join("data", "checkpoints", "_strategy9_ids.json")
    with open(path, encoding="utf-8") as f:
        ids = json.load(f)
    return {f"s9_{k}": v for k, v in ids.items() if k.endswith("_indicator")}


def _aggregate(batch_id):
    from data_engine import storage
    rows = storage.get_batch_results(batch_id)
    total_trades = wins = 0
    net_profit = gross_profit = gross_loss = 0.0
    worst_dd = 0.0
    n_symbols = 0
    for r in rows:
        m = r.get("metrics")
        if not m:
            continue
        n_symbols += 1
        total_trades += m.get("total_trades", 0)
        wins += m.get("wins", 0)
        net_profit += m.get("net_profit", 0.0)
        gross_profit += m.get("gross_profit", 0.0)
        gross_loss += m.get("gross_loss", 0.0)
        worst_dd = max(worst_dd, m.get("max_drawdown_pct", 0.0))
    win_rate = round(100.0 * wins / total_trades, 2) if total_trades else None
    profit_factor = round(gross_profit / gross_loss, 4) if gross_loss else None
    return {
        "symbols": n_symbols, "total_trades": total_trades, "win_rate": win_rate,
        "profit_factor": profit_factor, "net_profit": round(net_profit, 2),
        "worst_max_dd": round(worst_dd, 2),
    }


def main():
    which = sys.argv[1]
    label = sys.argv[2]

    from backtest_engine import strategy_library
    from backtest_engine.runner import run_mtf_batch
    from data_engine import storage
    from data_engine.config import DEFAULT_EXCHANGE

    if which == "laxman_dmc":
        ids = LAXMAN_DMC_IDS
    elif which == "new_batch":
        ids = dict(NEW_BATCH_IDS)
        ids.update(_load_strategy9_indicator_ids())
    else:
        raise SystemExit(f"unknown set: {which}")

    SETTINGS = {"initial_balance": 1000.0, "commission_pct": 0.1,
                "slippage_pct": 0.05, "position_size_pct": 10.0}

    symbols = storage.load_symbols(DEFAULT_EXCHANGE)
    print(f"Coin universe: {len(symbols)} symbols on {DEFAULT_EXCHANGE}", flush=True)

    results = {}
    for name, sid in ids.items():
        cfg = strategy_library.load(sid)
        settings = dict(SETTINGS)
        settings["risk_pct"] = cfg.risk_pct
        print(f"\n=== [{which}/{label}] Running [{name}] {cfg.name} ({sid}) across {len(symbols)} coins ===", flush=True)
        batch_id = run_mtf_batch(cfg, DEFAULT_EXCHANGE, symbols, settings, use_multiprocessing=True)
        agg = _aggregate(batch_id)
        print(f"[{name}] batch_id = {batch_id}  agg={agg}", flush=True)
        results[name] = {"strategy_id": sid, "batch_id": batch_id, "agg": agg}

    out_path = os.path.join("data", "checkpoints", f"_item2_{which}_{label}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print("\nDONE:", json.dumps(results, indent=2, default=str), flush=True)


if __name__ == "__main__":
    main()
