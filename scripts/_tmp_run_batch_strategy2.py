"""Full 50-coin backtest for New Batch 5 Strategy 2 (FRVP Market Shape)."""
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

    sid = "433942cfbbe0"
    symbols = storage.load_symbols(DEFAULT_EXCHANGE)
    print(f"Coin universe: {len(symbols)} symbols on {DEFAULT_EXCHANGE}", flush=True)

    cfg = strategy_library.load(sid)
    settings = dict(SETTINGS)
    settings["risk_pct"] = cfg.risk_pct
    print(f"\n=== Running {cfg.name} across {len(symbols)} coins ===", flush=True)
    batch_id = run_mtf_batch(cfg, DEFAULT_EXCHANGE, symbols, settings, use_multiprocessing=True)
    print(f"batch_id = {batch_id}", flush=True)

    with open("data/checkpoints/_strategy2_batch_id.json", "w", encoding="utf-8") as f:
        json.dump({"strategy_id": sid, "batch_id": batch_id}, f, indent=2)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
