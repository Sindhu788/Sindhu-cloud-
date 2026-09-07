"""Full 50-coin backtest for New Batch 5 Strategy 5 (both TP variants)."""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    from backtest_engine import strategy_library
    from backtest_engine.runner import run_mtf_batch
    from data_engine import storage
    from data_engine.config import DEFAULT_EXCHANGE

    SETTINGS = {"initial_balance": 1000.0, "commission_pct": 0.1,
                "slippage_pct": 0.05, "position_size_pct": 10.0}

    ids = {"structure": "7c8a8f40ce2a", "fixed_2": "edb442d731aa"}
    symbols = storage.load_symbols(DEFAULT_EXCHANGE)
    print(f"Coin universe: {len(symbols)} symbols on {DEFAULT_EXCHANGE}", flush=True)

    results = {}
    for variant, sid in ids.items():
        cfg = strategy_library.load(sid)
        settings = dict(SETTINGS)
        settings["risk_pct"] = cfg.risk_pct
        print(f"\n=== Running [{variant}] {cfg.name} across {len(symbols)} coins ===", flush=True)
        batch_id = run_mtf_batch(cfg, DEFAULT_EXCHANGE, symbols, settings, use_multiprocessing=True)
        print(f"[{variant}] batch_id = {batch_id}", flush=True)
        results[variant] = {"strategy_id": sid, "batch_id": batch_id}

    with open("data/checkpoints/_strategy5_batch_ids.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("\nDONE:", json.dumps(results, indent=2), flush=True)


if __name__ == "__main__":
    main()
