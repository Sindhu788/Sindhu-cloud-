"""Final Audit runner (not part of the app) -- runs the unified Engine
Health Report against real saved strategies on real candle data and
prints Strategy/Data/Execution/PnL/Trade/Statistics verification plus one
Overall Engine Status per BACKTESTING_MASTER_SPEC.md's ENGINE HEALTH
REPORT section.

Usage: python scripts/run_engine_health_report.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest_engine import strategy_library
from backtest_engine.mtf_context import MultiTimeframeContext
from backtest_engine.engine_health_report import run_engine_health_report
from data_engine.resample import get_ohlcv

TARGETS = [
    ("d0ba7163d890", "Liquidity Sweeps", ["BTCUSDT", "ETHUSDT"]),
    ("41a342bd1854", "PDH-PDL Signal Candle Strategy", ["BTCUSDT"]),
    ("440e8e3db0f0", "Multi-Timeframe Trend-Pullback Strategy", ["BTCUSDT"]),
]

SETTINGS = {"initial_balance": 1000.0, "risk_pct": 1.0, "commission_pct": 0.1,
            "slippage_pct": 0.05, "position_size_pct": 10.0}


def main():
    overall_pass = True
    summary_rows = []

    for strategy_id, name, symbols in TARGETS:
        cfg = strategy_library.load(strategy_id)
        entry_tf = cfg.timeframes.get("entry", "1m")
        for symbol in symbols:
            print(f"\n{'=' * 70}\nENGINE HEALTH: {name} | {symbol}\n{'=' * 70}")
            ctx = MultiTimeframeContext("binance", symbol, cfg.timeframes, None, None)
            if ctx.is_empty():
                print(f"  (no data for {symbol}, skipping)")
                continue

            raw_entry_df = get_ohlcv("binance", symbol, entry_tf)
            raw_1m_df = get_ohlcv("binance", symbol, "1m") if entry_tf != "1m" else None

            report = run_engine_health_report(
                cfg, ctx, dict(SETTINGS), symbol=symbol,
                raw_entry_df=raw_entry_df, entry_interval=entry_tf, raw_1m_df=raw_1m_df,
            )

            print(f"  Overall Engine Status: {report['overall_status']}")
            for sec_name, sec in report["sections"].items():
                status = sec["status"]
                extra = ""
                if sec_name == "trade_verification":
                    extra = f" ({sec['trade_count']} trades)"
                print(f"    {sec_name:<24} {status}{extra}")
                if status == "FAIL":
                    for key in ("issues", "rules_skipped", "missing_candles", "duplicate_candles",
                                "invalid_timestamps", "corrupted_ohlc"):
                        val = sec.get(key)
                        if val:
                            shown = val[:5]
                            print(f"        {key}: {len(val)} found, first few: {shown}")
                    if sec.get("resampling_check", {}).get("mismatches"):
                        mm = sec["resampling_check"]["mismatches"]
                        print(f"        resampling mismatches: {len(mm)}, first few: {mm[:5]}")

            summary_rows.append((name, symbol, report["overall_status"]))
            if report["overall_status"] != "PASS":
                overall_pass = False

    print(f"\n\n{'=' * 70}\nSUMMARY\n{'=' * 70}")
    for name, symbol, status in summary_rows:
        print(f"{name:<45} {symbol:<10} {status}")

    print(f"\nFINAL ENGINE HEALTH VERDICT: {'PASS' if overall_pass else 'FAIL'}")


if __name__ == "__main__":
    main()
