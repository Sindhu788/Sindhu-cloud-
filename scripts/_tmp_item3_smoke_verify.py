"""Item 3 (continuation structure-TP fix) verification: single-coin
(BTCUSDT) smoke test for each representative affected strategy, before
and after the fix -- full 50-coin backtests for all ~22 affected ids
would take hours on this machine's tight RAM/CPU budget, so this uses the
same fast single-symbol technique the original New Batch 5 work used for
its own initial sanity checks (scripts/_tmp_smoke_strategy*.py), one
representative id per concept family (the confirmation-strictness
variants of the same concept share the identical entry/defect logic, so
they would show the same before/after pattern).

Usage: python scripts/_tmp_item3_smoke_verify.py <label>
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SYMBOL = "BTCUSDT"
EXCHANGE = "binance"
SETTINGS = {"initial_balance": 1000.0, "commission_pct": 0.1, "slippage_pct": 0.05, "position_size_pct": 10.0}

REPRESENTATIVE_IDS = {
    "mss_reversal": "87c0c79ac0cb",
    "sr_breakout": "b4caef4ee47d",
    "range_breakout_volume_confirm": "8a048e8a2224",
    "donchian_lwti_volume_confluence": "0113516effdb",
    "htf_ltf_fvg_ob_confluence": "45040c58cf5a",
    "fvg_momentum_pullback_structure": "df643d86c987",
    "fvg_pure_inverse_structure": "7c8a8f40ce2a",
    "ema_smc_hybrid": "86ceac60820b",
    "fvg_equilibrium_entry": "143a732de079",
}


def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "run"
    from backtest_engine import strategy_library
    from backtest_engine.mtf_context import MultiTimeframeContext
    from backtest_engine.engine_health_report import run_engine_health_report
    from data_engine.resample import get_ohlcv

    results = {}
    for name, sid in REPRESENTATIVE_IDS.items():
        cfg = strategy_library.load(sid)
        entry_tf = cfg.timeframes.get("entry", "1h")
        settings = dict(SETTINGS)
        settings["risk_pct"] = cfg.risk_pct

        ctx = MultiTimeframeContext(EXCHANGE, SYMBOL, cfg.timeframes, None, None)
        if ctx.is_empty():
            print(f"[{label}/{name}] NO DATA for {SYMBOL} at {cfg.timeframes}", flush=True)
            results[name] = {"strategy_id": sid, "error": "no_data"}
            continue

        raw_entry_df = get_ohlcv(EXCHANGE, SYMBOL, entry_tf)
        raw_1m_df = get_ohlcv(EXCHANGE, SYMBOL, "1m") if entry_tf != "1m" else None

        report = run_engine_health_report(
            cfg, ctx, settings, symbol=SYMBOL,
            raw_entry_df=raw_entry_df, entry_interval=entry_tf, raw_1m_df=raw_1m_df,
        )
        stats = report["sections"]["statistics_verification"]["metrics"]
        summary = {
            "strategy_id": sid, "name": cfg.name, "trades": stats["total_trades"],
            "win_rate": stats["win_rate"], "profit_pct": stats["profit_pct"],
            "profit_factor": stats["profit_factor"], "max_dd": stats["max_drawdown_pct"],
            "engine_health": report["overall_status"],
        }
        print(f"[{label}/{name}] {json.dumps(summary, default=str)}", flush=True)
        results[name] = summary

    with open(f"data/checkpoints/_item3_smoke_{label}.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)


if __name__ == "__main__":
    main()
