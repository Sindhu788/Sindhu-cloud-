"""Runs a full backtest + Engine Health Report for EVERY strategy in the
library currently marked READY (passes both the automatic safety check
and the validator) -- one at a time, on real BTCUSDT historical data
(full available history), saving every result to disk as it completes so
progress survives even if the whole run is interrupted.

For each strategy this captures: trade count, win rate, PnL % and
absolute, profit factor, max drawdown, and the full six-dimension Engine
Health Report status (Strategy/Data/Execution/PnL/Trade/Statistics
verification) -- so a genuine bug (wrong PnL math, a rule that's never
actually enforced, a trade that doesn't match its own entry/exit data) is
caught structurally, not just eyeballed from the trade count.

Usage: python scripts/run_all_ready_backtests.py
Progress: data/history/all_ready_backtest_results.json (updated after
every strategy -- safe to read while this is still running)
"""
import sys
import os
import json
import time
import traceback
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_engine import paths
from backtest_engine import strategy_library, validator
from backtest_engine.strategy_safety_check import run_safety_check
from backtest_engine.mtf_context import MultiTimeframeContext
from backtest_engine.engine_health_report import run_engine_health_report
from data_engine.resample import get_ohlcv

SYMBOL = "BTCUSDT"
EXCHANGE = "binance"
SETTINGS = {"initial_balance": 1000.0, "risk_pct": 1.0, "commission_pct": 0.1,
            "slippage_pct": 0.05, "position_size_pct": 10.0}
RESULTS_PATH = os.path.join(paths.HISTORY_DIR, "all_ready_backtest_results.json")


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _ready_strategies():
    out = []
    for meta in strategy_library.list_all():
        cfg = strategy_library.load(meta["id"])
        if run_safety_check(cfg)["passed"] and not validator.validate(cfg):
            out.append((meta["id"], cfg))
    return out


def _run_one(strategy_id, cfg):
    entry_tf = cfg.timeframes.get("entry", "1m")
    t0 = time.time()
    settings = dict(SETTINGS)
    if cfg.risk_pct:
        settings["risk_pct"] = cfg.risk_pct

    ctx = MultiTimeframeContext(EXCHANGE, SYMBOL, cfg.timeframes, None, None)
    if ctx.is_empty():
        return {"status": "no_data", "reason": f"No {SYMBOL} candle data for this timeframe combination."}

    raw_entry_df = get_ohlcv(EXCHANGE, SYMBOL, entry_tf)
    raw_1m_df = get_ohlcv(EXCHANGE, SYMBOL, "1m") if entry_tf != "1m" else None

    report = run_engine_health_report(
        cfg, ctx, settings, symbol=SYMBOL,
        raw_entry_df=raw_entry_df, entry_interval=entry_tf, raw_1m_df=raw_1m_df,
    )
    stats = report["sections"]["statistics_verification"]["metrics"]
    elapsed = round(time.time() - t0, 1)

    return {
        "status": "completed",
        "elapsed_seconds": elapsed,
        "overall_engine_status": report["overall_status"],
        "sections": {name: sec["status"] for name, sec in report["sections"].items()},
        "section_details": {
            name: {k: v for k, v in sec.items() if k not in ("metrics",)}
            for name, sec in report["sections"].items() if sec["status"] == "FAIL"
        },
        "trades": stats["total_trades"],
        "win_rate_pct": stats["win_rate"],
        "profit_pct": stats["profit_pct"],
        "net_profit": stats["net_profit"],
        "final_balance": stats["final_balance"],
        "profit_factor": stats["profit_factor"],
        "max_drawdown_pct": stats["max_drawdown_pct"],
    }


def _load_results():
    try:
        with open(RESULTS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"started_at": _now_iso(), "symbol": SYMBOL, "results": {}}


def _save_results(data):
    os.makedirs(paths.HISTORY_DIR, exist_ok=True)
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def main():
    targets = _ready_strategies()
    data = {"started_at": _now_iso(), "symbol": SYMBOL, "total": len(targets), "results": {}}
    print(f"Found {len(targets)} READY strategies. Testing each on real {SYMBOL} data (full history).\n", flush=True)

    for i, (sid, cfg) in enumerate(targets, 1):
        print(f"[{i}/{len(targets)}] {cfg.name} ({sid}) -- entry={cfg.timeframes.get('entry')} ...", flush=True)
        try:
            result = _run_one(sid, cfg)
        except Exception as exc:
            result = {
                "status": "error",
                "reason": str(exc),
                "traceback": traceback.format_exc(),
            }
        result["name"] = cfg.name
        result["timeframes"] = cfg.timeframes
        data["results"][sid] = result
        _save_results(data)

        if result["status"] == "completed":
            print(f"    -> {result['trades']} trades, {result['win_rate_pct']}% win, "
                  f"{result['profit_pct']}% PnL, engine_status={result['overall_engine_status']} "
                  f"({result['elapsed_seconds']}s)", flush=True)
            if result["overall_engine_status"] != "PASS":
                for name, detail in result["section_details"].items():
                    print(f"    !! {name} FAILED: {json.dumps(detail, default=str)[:300]}", flush=True)
        else:
            print(f"    -> {result['status']}: {result.get('reason')}", flush=True)

    data["finished_at"] = _now_iso()
    _save_results(data)

    completed = [r for r in data["results"].values() if r["status"] == "completed"]
    failed = [r for r in data["results"].values() if r["status"] != "completed"]
    engine_pass = [r for r in completed if r["overall_engine_status"] == "PASS"]
    engine_fail = [r for r in completed if r["overall_engine_status"] != "PASS"]

    print("\n" + "=" * 78)
    print("SUMMARY")
    print("=" * 78)
    print(f"Total READY strategies: {len(targets)}")
    print(f"Backtest completed:     {len(completed)}")
    print(f"Backtest could not run: {len(failed)}")
    for r in failed:
        print(f"  - {r['name']}: {r['status']} ({r.get('reason')})")
    print(f"\nOf the {len(completed)} that ran:")
    print(f"  Engine Health PASS (every dimension clean): {len(engine_pass)}")
    print(f"  Engine Health FAIL (a genuine issue found):  {len(engine_fail)}")
    for r in engine_fail:
        print(f"    - {r['name']}: failing sections = "
              f"{[k for k, v in r['sections'].items() if v == 'FAIL']}")

    print(f"\nFull results saved to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
