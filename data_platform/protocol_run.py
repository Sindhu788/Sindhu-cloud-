"""Backtest protocol runner (Steps 17-18). Runs every enabled strategy EXACTLY AS IT IS (no parameter is ever changed) over the development period
(everything before the sealed holdout) for the N most liquid coins and stores the trades. Walk-forward windows are applied afterwards by entry time
(valid because nothing is trained or tuned: the same fixed strategy is simply scored window by window).
Usage (venv with pandas+pyarrow, e.g. D:\\sindhu_venv_bt):
  python -m data_platform.protocol_run --coins 10 --workers 3 [--strategies id1,id2] [--out D:\\sindhu_data\\experiments]
Environment is set here: SINDHU_BACKTEST_SOURCE=dataplatform, scratch SINDHU_DATA_DIR, strategy library dir. The holdout is never read."""
import argparse
import datetime as dt
import gzip
import json
import multiprocessing as mp
import os
import sys
import time

os.environ.setdefault("SINDHU_BACKTEST_SOURCE", "dataplatform")
os.environ.setdefault("SINDHU_DATA_DIR", r"D:\sindhu_runtime\dp_bt_data")
os.environ.setdefault("SINDHU_STRATEGY_LIBRARY_DIR", r"D:\sindhu_runtime\strategy_library")


def _init_worker():
    if os.environ.get("SINDHU_SANDBOX") == "1":          # candidate evaluation: workers cannot reach any network either
        from data_platform import sandbox
        sandbox.lock_network()
    import ctypes
    try:
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000)     # below normal: the laptop stays usable
    except Exception:
        pass


def _detach(argv):
    import subprocess
    flags = 0x00000008 | 0x00000200 | 0x08000000
    cmd = [sys.executable, "-m", "data_platform.protocol_run"] + [a for a in argv if a != "--detach"]
    cwd = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        p = subprocess.Popen(cmd, creationflags=flags | 0x01000000, close_fds=True, stdin=subprocess.DEVNULL, stdout=open(os.path.join(os.environ.get("SINDHU_DATA_ROOT", r"D:\sindhu_data"), "logs", "protocol_run.log"), "ab"), stderr=subprocess.STDOUT, cwd=cwd)
    except OSError:
        p = subprocess.Popen(cmd, creationflags=flags, close_fds=True, stdin=subprocess.DEVNULL, stdout=open(os.path.join(os.environ.get("SINDHU_DATA_ROOT", r"D:\sindhu_data"), "logs", "protocol_run.log"), "ab"), stderr=subprocess.STDOUT, cwd=cwd)
    return p.pid


def run_one(args):
    """One (strategy, coin) backtest over the development period. Returns a small summary dict; trades go to a gzip file."""
    sid, symbol, rank, start_ms, end_ms, out_dir = args
    path = os.path.join(out_dir, "trades", sid, f"{symbol}.json.gz")
    if os.path.exists(path):
        return {"sid": sid, "symbol": symbol, "skipped": True}
    t0 = time.time()
    from backtest_engine import strategy_library
    from backtest_engine.configured_strategy import ConfiguredStrategy
    from backtest_engine.engine import run_backtest
    from backtest_engine.mtf_context import MultiTimeframeContext
    from data_platform import backtest_source, cost_model, experiments
    cfg = strategy_library.load(sid)
    try:
        ctx = MultiTimeframeContext("binance", symbol, cfg.timeframes, start_ms, end_ms)
        if ctx.is_empty():
            summary = {"sid": sid, "symbol": symbol, "error": "no data", "seconds": round(time.time() - t0, 1)}
            return summary
        entry = ctx.frames["entry"]
        m1 = backtest_source.loader().load(symbol, "1m", start=start_ms, end=min(end_ms, start_ms + 30 * 86_400_000))
        rng = cost_model.median_range_pct_1m(m1["high"].to_numpy(), m1["low"].to_numpy()) if len(m1) else 0.1
        costs = cost_model.settings_for(rank, rng)
        settings = {"initial_balance": 1000.0, "position_size_pct": 10.0, "risk_pct": cfg.risk_pct or 1.0, **costs}
        strat = ConfiguredStrategy(cfg)
        merged = strat.prepare_context(ctx)
        trades, equity, final = run_backtest(merged, strat, settings)
    except Exception as e:      # a strategy that cannot run is reported, never hidden
        return {"sid": sid, "symbol": symbol, "error": f"{type(e).__name__}: {str(e)[:120]}", "seconds": round(time.time() - t0, 1)}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    keep = ["side", "entry_time", "exit_time", "entry_price", "exit_price", "pnl", "gross_pnl", "commission_cost", "slippage_cost", "spread_cost",
            "risk_amount", "exit_reason", "is_partial"]
    slim = [{k: t.get(k) for k in keep} for t in trades]
    tmp = path + ".tmp"
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump({"strategy_id": sid, "symbol": symbol, "rank": rank, "costs": costs, "start_ms": start_ms, "end_ms": end_ms, "trades": slim}, f)
    os.replace(tmp, path)
    dv = backtest_source.loader().data_version([symbol])
    experiments.record({"kind": "dev", "strategy_id": sid, "strategy_name": cfg.name, "config_hash": experiments.config_hash(cfg.to_dict()),
                        "code_commit": experiments.code_commit(), "data_version": dv, "universe": "latest", "symbol": symbol, "window_start": start_ms,
                        "window_end": end_ms, "cost_json": costs, "n_trades": len(slim), "metrics_json": {}, "trades_path": path,
                        "result_hash": experiments.result_hash(slim)})
    return {"sid": sid, "symbol": symbol, "trades": len(slim), "seconds": round(time.time() - t0, 1)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--coins", type=int, default=10)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--strategies", default="")
    ap.add_argument("--out", default=None)
    ap.add_argument("--start", default=None, help="development start (UTC date); default = first day of the dataset")
    ap.add_argument("--detach", action="store_true")
    a = ap.parse_args(argv)
    if a.detach:
        print("started detached, pid", _detach(sys.argv[1:]))
        return
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from data_platform import backtest_source, store, universe
    root = store.root()
    out = a.out or os.path.join(root, "experiments")
    L = backtest_source.loader()
    h = L.holdout_start_ms
    uni = universe.load_latest(root)
    syms = uni["symbols"][: a.coins]
    strategies = json.load(open(os.path.join(out, "strategies_42.json"), encoding="utf-8"))
    ids = [s["id"] for s in strategies]
    if a.strategies:
        ids = [i for i in ids if i in set(a.strategies.split(","))]
    first = min(int(v["first_ts"]) for k, v in L.manifest.snapshot().items() if v.get("status") == "ok" and len(k.split("/")) == 2 and len(k.split("/")[1]) == 7)
    start_ms = int(dt.datetime.fromisoformat(a.start).replace(tzinfo=dt.timezone.utc).timestamp() * 1000) if a.start else first
    jobs = [(sid, s, r + 1, start_ms, h, out) for sid in ids for r, s in enumerate(syms)]
    print(f"{len(jobs)} runs: {len(ids)} strategies x {len(syms)} coins, development window "
          f"{dt.datetime.fromtimestamp(start_ms / 1000, dt.timezone.utc):%Y-%m-%d} .. {dt.datetime.fromtimestamp(h / 1000, dt.timezone.utc):%Y-%m-%d} (holdout sealed)", flush=True)
    done = 0
    prog = os.path.join(out, "protocol_progress.json")
    t0 = time.time()
    with mp.Pool(a.workers, initializer=_init_worker) as pool:
        for res in pool.imap_unordered(run_one, jobs):
            done += 1
            if done % 5 == 0 or "error" in res:
                json.dump({"done": done, "total": len(jobs), "percent": round(100 * done / len(jobs), 1), "elapsed_min": round((time.time() - t0) / 60, 1),
                           "last": res}, open(prog, "w"))
            if "error" in res:
                print("ERROR", res, flush=True)
    json.dump({"done": done, "total": len(jobs), "percent": 100.0, "elapsed_min": round((time.time() - t0) / 60, 1), "finished": True}, open(prog, "w"))
    print("finished", done, "runs in", round((time.time() - t0) / 60, 1), "min")


if __name__ == "__main__":
    mp.freeze_support()
    main()
