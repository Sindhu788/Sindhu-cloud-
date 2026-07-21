"""One-off verification script (not part of the app) for the multi-timeframe
enforcement fix: runs BEFORE (role stripped) vs AFTER (current, backfilled
role) for 3 real saved strategies on the same 10-coin subset, and traces a
handful of real AFTER-run trades to show bias/trend/analysis values were
actually referenced in the entry decision, not just fetched and discarded.
"""
import copy
import json
import sqlite3
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from backtest_engine import strategy_library, runner
from backtest_engine.configured_strategy import ConfiguredStrategy
from backtest_engine.mtf_context import MultiTimeframeContext
from backtest_engine.engine import run_backtest as engine_run_backtest
from data_engine import storage

COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
         "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "LTCUSDT"]
SETTINGS = {"initial_balance": 1000.0, "risk_pct": 1.0, "commission_pct": 0.1,
            "slippage_pct": 0.05, "position_size_pct": 10.0}

TARGETS = [
    ("d0ba7163d890", "Liquidity Sweeps"),                    # entry=1m, bias/trend/analysis
    ("41a342bd1854", "PDH-PDL Signal Candle Strategy"),      # entry=1m, analysis=1d
    ("9f2c339a4d6a", "Daily High-Low Liquidity Strategy"),   # entry=5m (non-1m!), analysis=1h
]


def strip_roles(config):
    stripped = copy.deepcopy(config)
    for bucket in ("entry_conditions", "exit_conditions", "confirmation_conditions"):
        for cond in getattr(stripped, bucket):
            cond.role = None
    return stripped


def summarize(batch_id):
    conn = sqlite3.connect("data/database/sindhu.db")
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*), SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END), ROUND(SUM(pnl),2) "
                "FROM backtest_trades WHERE batch_id=?", (batch_id,))
    n, w, p = cur.fetchone()
    conn.close()
    n = n or 0
    w = w or 0
    p = p or 0.0
    wr = (100 * w / n) if n else 0.0
    return n, w, wr, p


def trace_trades(batch_id, symbol="BTCUSDT", n=5):
    conn = sqlite3.connect("data/database/sindhu.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT symbol, trade_num, side, entry_time, entry_price, exit_price, pnl, exit_reason, entry_reason "
                "FROM backtest_trades WHERE batch_id=? AND symbol=? ORDER BY trade_num LIMIT ?", (batch_id, symbol, n))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def trace_with_htf_values(config, symbol="BTCUSDT", n=5):
    """Direct, single-symbol trace (bypassing the DB) that prints each
    trade's entry_reason alongside the ACTUAL bias/trend/analysis column
    values at that same bar -- the direct proof that higher-timeframe data
    was read, not just fetched and discarded."""
    strat = ConfiguredStrategy(config)
    ctx = MultiTimeframeContext("binance", symbol, config.timeframes, None, None)
    if ctx.is_empty():
        print(f"    (no data for {symbol}, skipping direct trace)")
        return
    merged = strat.prepare_context(ctx)
    df = strat.prepare(merged)
    htf_cols = [c for c in df.columns if c.startswith(("bias_", "trend_", "analysis_")) and c.endswith("_close")]
    trades, _, _ = engine_run_backtest(df, strat, dict(SETTINGS))
    print(f"    (direct {symbol} trace, {len(trades)} trades total, showing first {n})")
    for t in trades[:n]:
        ts = pd.to_datetime(t["entry_time"], unit="ms", utc=True)
        idx = df.index.get_indexer([ts], method="nearest")[0]
        row = df.iloc[idx]
        htf_vals = {c: row.get(c) for c in htf_cols}
        print(f"      {ts} {t['side']} entry={t['entry_price']:.6f} reason={t['entry_reason']} | HTF values at this bar: {htf_vals}")


def run_variant(label, strategy_id, config):
    batch_id = runner.run_mtf_batch(
        config, "binance", COINS, dict(SETTINGS),
        log=lambda msg: None, use_multiprocessing=False,
    )
    n, w, wr, p = summarize(batch_id)
    print(f"  [{label}] batch={batch_id} trades={n} wins={w} win_rate={wr:.2f}% pnl=${p}")
    return batch_id, n, w, wr, p


def main():
    for strategy_id, name in TARGETS:
        print(f"\n=== {name} ({strategy_id}) ===")
        after_cfg = strategy_library.load(strategy_id)
        roles_used = sorted({c.role for bucket in ("entry_conditions", "exit_conditions", "confirmation_conditions")
                              for c in getattr(after_cfg, bucket) if c.type == "concept" and c.role})
        print(f"  timeframes: {after_cfg.timeframes}")
        print(f"  roles actually used by conditions: {roles_used or 'NONE'}")

        before_cfg = strip_roles(after_cfg)
        before_batch, *_ = run_variant("BEFORE (role stripped)", strategy_id, before_cfg)
        after_batch, *_ = run_variant("AFTER  (current, backfilled)", strategy_id, after_cfg)

        print("  --- 5 real AFTER-run trades (portfolio batch, BTCUSDT) ---")
        for t in trace_trades(after_batch):
            print(f"    {t['symbol']} #{t['trade_num']} {t['side']} entry={t['entry_price']:.6f} "
                  f"exit={t['exit_price']}  pnl={round(t['pnl'],2) if t['pnl'] is not None else None} "
                  f"reason={t['exit_reason']} | entry_reason={t['entry_reason']}")

        print("  --- direct trace with actual higher-timeframe column values ---")
        trace_with_htf_values(after_cfg)

        print(f"  BEFORE_BATCH={before_batch} AFTER_BATCH={after_batch}")


if __name__ == "__main__":
    main()
