"""One-off runner (not part of the app) for Phase 2's Verification Engine
-- runs it against real saved strategies on real candle data and prints a
full Verification Report per BACKTESTING_MASTER_SPEC.md Requirements
12/13/16.

Usage: python scripts/run_verification.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest_engine import strategy_library
from backtest_engine.mtf_context import MultiTimeframeContext
from backtest_engine.verification_engine import run_verification

TARGETS = [
    ("d0ba7163d890", "Liquidity Sweeps", ["BTCUSDT", "ETHUSDT"]),
    ("41a342bd1854", "PDH-PDL Signal Candle Strategy", ["BTCUSDT"]),
    ("9f2c339a4d6a", "Daily High-Low Liquidity Strategy", ["BTCUSDT"]),
    ("440e8e3db0f0", "Multi-Timeframe Trend-Pullback Strategy", ["BTCUSDT"]),
]

SETTINGS = {"initial_balance": 1000.0, "risk_pct": 1.0, "commission_pct": 0.1,
            "slippage_pct": 0.05, "position_size_pct": 10.0}


def main():
    overall_pass = True
    summary_rows = []

    for strategy_id, name, symbols in TARGETS:
        cfg = strategy_library.load(strategy_id)
        for symbol in symbols:
            print(f"\n{'=' * 70}\nVERIFYING: {name} | {symbol}\n{'=' * 70}")
            ctx = MultiTimeframeContext("binance", symbol, cfg.timeframes, None, None)
            if ctx.is_empty():
                print(f"  (no data for {symbol}, skipping)")
                continue
            report = run_verification(cfg, ctx, dict(SETTINGS), symbol=symbol)

            print(f"  Trades: {report['trade_count']}  |  Overall: {report['overall_status']}")

            skipped = report["rules_skipped"]
            if skipped:
                print(f"  RULES SKIPPED ({len(skipped)}):")
                for f in skipped:
                    print(f"    - [{f['bucket']}#{f['index']}] {f['condition']}: {f['reason']}")
            else:
                print("  Rule coverage: all rules reached by the Rule Engine.")

            never_true = [f for f in report["rule_coverage"] if f["status"] == "NEVER_TRUE"]
            if never_true:
                print(f"  Rules evaluated but never true ({len(never_true)}, informational):")
                for f in never_true:
                    print(f"    - [{f['bucket']}#{f['index']}] {f['condition']}: {f['reason']}")

            validation = report["trade_validation"]
            if validation["issues_by_trade"]:
                print(f"  TRADE VALIDATION FAILURES ({len(validation['issues_by_trade'])} of {validation['trade_count']} trades):")
                for trade_num, issues in list(validation["issues_by_trade"].items())[:10]:
                    print(f"    Trade #{trade_num}:")
                    for issue in issues:
                        print(f"      - {issue}")
            else:
                print(f"  Trade validation: {validation['trade_count']}/{validation['trade_count']} trades verified clean.")

            if validation["duplicate_trades"]:
                print(f"  DUPLICATE TRADES: {validation['duplicate_trades']}")

            summary_rows.append((name, symbol, report["trade_count"], report["overall_status"], len(skipped),
                                  len(validation["issues_by_trade"])))
            if report["overall_status"] != "PASS":
                overall_pass = False

    print(f"\n\n{'=' * 70}\nSUMMARY\n{'=' * 70}")
    print(f"{'Strategy':<45} {'Symbol':<10} {'Trades':>7} {'Status':>7} {'Skipped':>8} {'BadTrades':>10}")
    for name, symbol, trades, status, n_skipped, n_bad in summary_rows:
        print(f"{name:<45} {symbol:<10} {trades:>7} {status:>7} {n_skipped:>8} {n_bad:>10}")

    print(f"\nFINAL VERDICT: {'PASS' if overall_pass else 'FAIL'}")


if __name__ == "__main__":
    main()
