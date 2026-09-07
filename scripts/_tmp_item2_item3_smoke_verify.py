"""Combined smoke-test verification for Item 2 (remaining S9 indicator-exit
variants, post-fix only -- 50-coin full runs kept getting cut off by
repeated environment interruptions; single-coin BTCUSDT is fast enough to
survive) and Item 3 (representative continuation-strategy fix, one id per
concept family). Same technique as the original batch's own initial
sanity checks (scripts/_tmp_smoke_strategy*.py)."""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SYMBOL = "BTCUSDT"
EXCHANGE = "binance"
SETTINGS = {"initial_balance": 1000.0, "commission_pct": 0.1, "slippage_pct": 0.05, "position_size_pct": 10.0}

ITEM2_REMAINING_S9_IDS = {
    "s9_15m_indicator": "04598eaca214",
    "s9_1h_indicator": "ca0777badd9f",
    "s9_1d_indicator": "d781b37694ef",
}

ITEM3_REPRESENTATIVE_IDS = {
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
    from backtest_engine import strategy_library
    from backtest_engine.mtf_context import MultiTimeframeContext
    from backtest_engine.engine_health_report import run_engine_health_report
    from data_engine.resample import get_ohlcv

    all_ids = {}
    all_ids.update({f"item2_{k}": v for k, v in ITEM2_REMAINING_S9_IDS.items()})
    all_ids.update({f"item3_{k}": v for k, v in ITEM3_REPRESENTATIVE_IDS.items()})

    results = {}
    for name, sid in all_ids.items():
        try:
            cfg = strategy_library.load(sid)
            entry_tf = cfg.timeframes.get("entry", "1h")
            settings = dict(SETTINGS)
            settings["risk_pct"] = cfg.risk_pct

            ctx = MultiTimeframeContext(EXCHANGE, SYMBOL, cfg.timeframes, None, None)
            if ctx.is_empty():
                print(f"[{name}] NO DATA for {SYMBOL} at {cfg.timeframes}", flush=True)
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
        except Exception as e:
            summary = {"strategy_id": sid, "error": repr(e)}
        print(f"[{name}] {json.dumps(summary, default=str)}", flush=True)
        results[name] = summary
        with open("data/checkpoints/_item2_item3_smoke_verify.json", "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)

    print("DONE", flush=True)


if __name__ == "__main__":
    main()
