"""Quick single-symbol (BTCUSDT) sanity check for New Batch 5 Strategy 6
before committing to the full 50-coin backtest."""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest_engine import strategy_library
from backtest_engine.mtf_context import MultiTimeframeContext
from backtest_engine.engine_health_report import run_engine_health_report
from data_engine.resample import get_ohlcv

SYMBOL = "BTCUSDT"
EXCHANGE = "binance"
SETTINGS = {"initial_balance": 1000.0, "risk_pct": 1.0, "commission_pct": 0.1,
            "slippage_pct": 0.05, "position_size_pct": 10.0}

ids = {"loose": "90a2331a3b1c", "strict": "52c6ab43fd4a"}

for variant, sid in ids.items():
    cfg = strategy_library.load(sid)
    entry_tf = cfg.timeframes.get("entry", "1h")
    settings = dict(SETTINGS)
    settings["risk_pct"] = cfg.risk_pct

    ctx = MultiTimeframeContext(EXCHANGE, SYMBOL, cfg.timeframes, None, None)
    raw_entry_df = get_ohlcv(EXCHANGE, SYMBOL, entry_tf)
    raw_1m_df = get_ohlcv(EXCHANGE, SYMBOL, "1m") if entry_tf != "1m" else None

    report = run_engine_health_report(
        cfg, ctx, settings, symbol=SYMBOL,
        raw_entry_df=raw_entry_df, entry_interval=entry_tf, raw_1m_df=raw_1m_df,
    )
    stats = report["sections"]["statistics_verification"]["metrics"]
    print(f"\n=== [{variant}] {cfg.name} ===")
    print("overall_status:", report["overall_status"])
    for name, sec in report["sections"].items():
        print(f"  {name}: {sec['status']}")
        if sec["status"] == "FAIL":
            print("    detail:", json.dumps({k: v for k, v in sec.items() if k not in ("metrics",)}, default=str)[:1000])
    print("trades:", stats["total_trades"], "win_rate:", stats["win_rate"],
          "profit_pct:", stats["profit_pct"], "profit_factor:", stats["profit_factor"],
          "max_dd:", stats["max_drawdown_pct"])
