"""Real, end-to-end demonstration of Walk-Forward Testing against an
actual saved "Ready" library strategy -- not a mock. Prints the real
Training Period numbers, the real Testing Period numbers, and the
verdict with its reason, exactly as the automation pipeline's new
Walk-Forward stage would produce and save.

Usage: python scripts/run_walk_forward_demo.py <strategy_id> [symbol]
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest_engine import strategy_library
from automation_pipeline import walk_forward


def main():
    strategy_id = sys.argv[1] if len(sys.argv) > 1 else "0cfffa6af923"
    symbol = sys.argv[2] if len(sys.argv) > 2 else "BTCUSDT"
    exchange = "binance"

    cfg = strategy_library.load(strategy_id)
    print(f"Strategy: {cfg.name} ({strategy_id})")
    print(f"Symbol: {symbol}  |  Timeframes: {cfg.timeframes}\n")

    settings = {"initial_balance": 1000.0, "risk_pct": cfg.risk_pct or 1.0,
                "commission_pct": 0.1, "slippage_pct": 0.05, "position_size_pct": 10.0}

    def log(msg):
        print(f"  {msg}", flush=True)

    result = walk_forward.run_walk_forward_test(cfg, exchange, symbol, settings, log_fn=log)

    print("\n" + "=" * 78)
    print("WALK-FORWARD TEST RESULT")
    print("=" * 78)
    print(json.dumps(result, indent=2, default=str))

    print("\n" + "=" * 78)
    print(f"VERDICT: {result['status']}")
    print(f"REASON:  {result['reason']}")
    print("=" * 78)

    strategy_library.save_walk_forward_result(strategy_id, result)
    print(f"\nSaved to strategy_library meta.json for {strategy_id} "
          f"(walk_forward_status={result['status']}) -- original strategy config/versions untouched.")


if __name__ == "__main__":
    main()
