"""Windows uses spawn (not fork) for multiprocessing -- run_mtf_batch's
ProcessPoolExecutor/Manager re-import this file as __mp_main__ in each
worker, so all top-level work MUST sit behind the __main__ guard or every
worker re-runs the whole script recursively."""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    from backtest_engine import strategy_library
    from backtest_engine.runner import run_mtf_batch
    from data_engine import storage
    from data_engine.config import DEFAULT_EXCHANGE
    import importlib.util

    spec = importlib.util.spec_from_file_location("item2rerun", "scripts/_tmp_item2_rerun.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    remaining = {
        "s9_15m_indicator": "04598eaca214",
        "s9_1h_indicator": "ca0777badd9f",
        "s9_1d_indicator": "d781b37694ef",
    }
    SETTINGS = {"initial_balance": 1000.0, "commission_pct": 0.1, "slippage_pct": 0.05, "position_size_pct": 10.0}
    symbols = storage.load_symbols(DEFAULT_EXCHANGE)
    print(f"Coin universe: {len(symbols)} symbols", flush=True)
    results = {}
    for name, sid in remaining.items():
        cfg = strategy_library.load(sid)
        settings = dict(SETTINGS)
        settings["risk_pct"] = cfg.risk_pct
        print(f"=== Running [{name}] {cfg.name} ({sid}) ===", flush=True)
        batch_id = run_mtf_batch(cfg, DEFAULT_EXCHANGE, symbols, settings, use_multiprocessing=True)
        agg = m._aggregate(batch_id)
        print(f"[{name}] batch_id={batch_id} agg={agg}", flush=True)
        results[name] = {"strategy_id": sid, "batch_id": batch_id, "agg": agg}

    with open("data/checkpoints/_item2_new_batch_post_fix_remaining2.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("DONE", json.dumps(results, indent=2), flush=True)


if __name__ == "__main__":
    main()
