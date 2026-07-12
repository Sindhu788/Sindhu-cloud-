import os
import threading
import time
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from datetime import datetime, timezone
from multiprocessing import Manager

from data_engine import storage
from data_engine.resample import get_ohlcv
from data_engine.logging_setup import log as default_log
from backtest_engine.engine import run_backtest
from backtest_engine.metrics import compute_metrics
from backtest_engine.mtf_worker import run_one_symbol


def new_batch_id():
    return datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6]


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


class _DirectCallbackQueue:
    """Queue-like adapter so mtf_worker.run_one_symbol's progress reporting
    is identical code whether running sequentially (direct callback, no
    real queueing needed) or in a subprocess (a real
    multiprocessing.Manager().Queue())."""

    def __init__(self, callback):
        self._callback = callback

    def put(self, msg):
        self._callback(msg)


def run_batch(strategy_class, exchange, symbols, timeframes, settings,
              start_ms=None, end_ms=None, batch_id=None,
              log=default_log, control=None, progress_cb=None, trade_cb=None):
    """Runs `strategy_class` across every (symbol, timeframe) combo.

    Passing an existing batch_id resumes it: combos already marked
    'completed' in backtest_results are skipped, so an interrupted run
    picks up exactly where it left off instead of repeating finished work.
    """
    strategy_name = strategy_class.name

    if batch_id is None:
        batch_id = new_batch_id()
        storage.create_batch(batch_id, strategy_name, exchange, settings, _now_iso())
        storage.register_strategy(strategy_name, strategy_class.__module__, _now_iso())
        log(f"Backtesting Started... (batch {batch_id})")
    else:
        existing = storage.get_batch(batch_id)
        if existing is None:
            storage.create_batch(batch_id, strategy_name, exchange, settings, _now_iso())
        log(f"Resuming batch {batch_id}...")

    combos = [(s, tf) for s in symbols for tf in timeframes]
    completed = storage.get_completed_result_keys(batch_id)
    remaining = [c for c in combos if c not in completed]

    total = len(combos)
    done_count = total - len(remaining)

    for symbol, timeframe in remaining:
        if control and control.should_stop():
            log("Stopped by user.")
            storage.update_batch_status(batch_id, "stopped", _now_iso())
            return batch_id
        if control:
            control.wait_if_paused()

        if progress_cb:
            progress_cb(done_count, total, symbol, timeframe)
        log(f"{symbol} {timeframe} Running...")

        try:
            df = get_ohlcv(exchange, symbol, timeframe, start_ms, end_ms)
            if df.empty:
                log(f"  {symbol} {timeframe}: no data, skipping")
                storage.save_result(batch_id, symbol, timeframe, "error", {"error": "no data"}, _now_iso())
                done_count += 1
                continue

            def _on_trade(trade, _symbol=symbol, _timeframe=timeframe):
                if trade_cb:
                    trade_cb(_symbol, _timeframe, trade)

            trades, equity_curve, _final_balance = run_backtest(
                df, strategy_class(), settings, control=control, on_trade=_on_trade,
            )
            metrics = compute_metrics(trades, equity_curve, settings["initial_balance"])
            storage.save_trades(batch_id, symbol, timeframe, trades)
            storage.save_result(batch_id, symbol, timeframe, "completed", metrics, _now_iso())
            log(
                f"Completed {symbol} {timeframe}  "
                f"(trades={metrics['total_trades']}, win_rate={metrics['win_rate']}%, profit={metrics['profit_pct']}%)"
            )
        except Exception as e:
            log(f"  {symbol} {timeframe}: ERROR {e!r}")
            storage.save_result(batch_id, symbol, timeframe, "error", {"error": repr(e)}, _now_iso())

        done_count += 1

    if control and control.should_stop():
        storage.update_batch_status(batch_id, "stopped", _now_iso())
    else:
        storage.update_batch_status(batch_id, "completed", _now_iso())
        log("Saving Results...")
        log("Backtest batch complete.")

    return batch_id


def run_mtf_batch(config, exchange, symbols, settings, start_ms=None, end_ms=None,
                   batch_id=None, log=default_log, control=None, progress_cb=None,
                   trade_cb=None, use_multiprocessing=True, max_workers=None):
    """Runs a parsed multi-timeframe StrategyConfig across multiple coins.

    Unlike run_batch, the timeframes are fixed by the strategy itself
    (bias/trend/analysis/entry/confirmation), so the only per-combo
    dimension left is the coin -- one (symbol, entry_timeframe) result per
    coin, same resumability guarantee as run_batch (completed coins are
    skipped on resume).

    When use_multiprocessing is True and there's more than one symbol left
    to run, each symbol's backtest runs in its own process (CPU-bound work,
    fully independent per symbol) while this process is the only one that
    ever writes to the database. Pause is not supported mid-flight in
    multiprocessing mode -- already-dispatched symbols keep computing in
    the background -- only Stop is honored between completions; run
    sequentially (use_multiprocessing=False) if you need true pause/resume
    responsiveness.
    """
    strategy_name = config.name
    entry_tf = config.timeframes.get("entry", "?")
    full_settings = dict(settings)
    full_settings["symbols"] = symbols
    full_settings["timeframes_by_role"] = dict(config.timeframes)

    if batch_id is None:
        batch_id = new_batch_id()
        storage.create_batch(batch_id, strategy_name, exchange, full_settings, _now_iso())
        storage.register_strategy(strategy_name, "backtest_engine.configured_strategy", _now_iso())
        log(f"Backtesting Started... (batch {batch_id})")
    else:
        existing = storage.get_batch(batch_id)
        if existing is None:
            storage.create_batch(batch_id, strategy_name, exchange, full_settings, _now_iso())
        log(f"Resuming batch {batch_id}...")

    completed = storage.get_completed_result_keys(batch_id)
    remaining = [s for s in symbols if (s, entry_tf) not in completed]
    total = len(symbols)
    done_count = total - len(remaining)
    config_dict = config.to_dict()
    batch_start_time = time.time()

    def _emit_progress(symbol, stage, bar_pct=None, trades_so_far=None):
        """Turns a raw {"stage", "bar_pct", "trades_so_far"} update for one
        coin into a progress_cb call, adding the coin-count-based ETA. Reads
        `done_count`/`total` live from the enclosing scope, so it always
        reflects the current progress even though it's called many times
        per coin (once per stage transition, and repeatedly while
        simulating bars)."""
        if not progress_cb:
            return
        eta_seconds = None
        if done_count > 0:
            elapsed = time.time() - batch_start_time
            eta_seconds = round((elapsed / done_count) * max(total - done_count, 0), 1)
        progress_cb(done_count, total, symbol, entry_tf, stage=stage,
                    bar_pct=bar_pct, trades_so_far=trades_so_far, eta_seconds=eta_seconds)

    def _save_and_report(symbol, result, error=None):
        if error is not None:
            # v8 Debug Mode: an uncaught exception escaping the worker
            # process itself (mtf_worker.py already catches everything it
            # can and reports {stage,function,reason,suggested_fix} instead
            # -- this branch is the outer safety net for anything that
            # still slips through, e.g. a pool-level pickling failure).
            log(f"  {symbol}: [unknown stage] ERROR {error!r}")
            storage.save_result(
                batch_id, symbol, entry_tf, "error",
                {
                    "error": repr(error), "stage": "unknown", "function": "run_batch (pool boundary)",
                    "reason": repr(error),
                    "suggested_fix": "Check server logs for the full traceback; this failure happened outside the normal per-symbol error handling.",
                },
                _now_iso(),
            )
            return
        if result["status"] == "error":
            stage = result.get("stage", "unknown")
            reason = result.get("reason", result.get("error", "error"))
            suggested_fix = result.get("suggested_fix", "")
            log(f"  {symbol}: [{stage}] {reason}" + (f" -- {suggested_fix}" if suggested_fix else "") + ", skipping")
            storage.save_result(
                batch_id, symbol, entry_tf, "error",
                {
                    "error": result.get("error"), "stage": stage,
                    "function": result.get("function", "run_one_symbol"),
                    "reason": reason, "suggested_fix": suggested_fix,
                },
                _now_iso(),
            )
            return
        storage.save_trades(batch_id, symbol, entry_tf, result["trades"])
        storage.save_result(batch_id, symbol, entry_tf, "completed", result["metrics"], _now_iso())
        if trade_cb:
            for t in result["trades"]:
                trade_cb(symbol, entry_tf, t)
        m = result["metrics"]
        if m["total_trades"] == 0 and result.get("condition_report"):
            storage.save_condition_report(batch_id, symbol, entry_tf, result["condition_report"], _now_iso())
            cr = result["condition_report"]
            per_cond = ", ".join(f"{pc['description']}={pc['true_bars']}" for pc in cr["per_condition"])
            log(f"  {symbol} {entry_tf}: 0 trades -- condition hits over {cr['total_bars']} bars: "
                f"{per_cond or 'no entry conditions'}; ALL TOGETHER={cr['all_together_bars']}")
        log(f"Completed {symbol} {entry_tf}  (trades={m['total_trades']}, win_rate={m['win_rate']}%, profit={m['profit_pct']}%)")

    sequential_leftover = list(remaining)

    if use_multiprocessing and len(remaining) > 1:
        # Each worker process re-imports pandas/numpy/ccxt and holds its own
        # full-history dataframe, so this is memory-bound as much as
        # CPU-bound. Capped at 4 regardless of core count -- uncapped
        # (cpu_count - 1) reliably exhausted RAM on an 8GB machine and
        # crashed several workers with MemoryError/BrokenProcessPool.
        max_workers = max_workers or max(1, min(4, (os.cpu_count() or 2) - 1))
        sequential_leftover = []
        pool_broken = False

        # A Manager().Queue() proxy is picklable across process boundaries
        # (unlike a plain callback), so each worker process can stream live
        # stage/bar-progress messages back to this process without any of
        # them ever touching the database themselves.
        manager = Manager()
        progress_queue = manager.Queue()
        stop_draining = threading.Event()

        def _drain_queue():
            # This thread must never die -- if it silently dies, the shared
            # progress_queue stops being drained and every subsequent status
            # update from every worker is lost. So the get() timeout/empty
            # case and the _emit_progress() call each get their own
            # try/except: an error updating UI progress is logged and
            # skipped, never allowed to stop the drain loop or the backtest.
            while not stop_draining.is_set():
                try:
                    msg = progress_queue.get(timeout=0.5)
                except Exception:
                    continue
                try:
                    _emit_progress(msg["symbol"], msg.get("stage"), msg.get("bar_pct"), msg.get("trades_so_far"))
                except Exception as e:
                    log(f"  [progress] _emit_progress failed (ignored, backtest continues): {e!r}")

        drain_thread = threading.Thread(target=_drain_queue, daemon=True)
        drain_thread.start()

        try:
            with ProcessPoolExecutor(max_workers=max_workers) as pool:
                futures = {
                    pool.submit(run_one_symbol, config_dict, exchange, s, settings, start_ms, end_ms, batch_id, progress_queue): s
                    for s in remaining
                }
                for future in as_completed(futures):
                    symbol = futures[future]

                    if pool_broken:
                        # the pool already died -- these symbols get retried
                        # sequentially below instead of all being marked failed.
                        sequential_leftover.append(symbol)
                        continue

                    log(f"{symbol} {entry_tf} Running...")
                    try:
                        result = future.result()
                        _save_and_report(symbol, result)
                        done_count += 1
                        _emit_progress(symbol, "completed", trades_so_far=len(result.get("trades") or []))
                    except BrokenProcessPool as e:
                        log(f"Multiprocessing pool failed ({e!r}) -- "
                            f"automatically continuing sequentially for the remaining coins.")
                        pool_broken = True
                        sequential_leftover.append(symbol)
                    except Exception as e:
                        _save_and_report(symbol, None, error=e)
                        done_count += 1
                        _emit_progress(symbol, "failed")

                    if control and control.should_stop():
                        log("Stopped by user.")
                        stop_draining.set()
                        for f in futures:
                            f.cancel()
                        storage.update_batch_status(batch_id, "stopped", _now_iso())
                        return batch_id
        finally:
            stop_draining.set()

    for symbol in sequential_leftover:
        if control and control.should_stop():
            log("Stopped by user.")
            storage.update_batch_status(batch_id, "stopped", _now_iso())
            return batch_id
        if control:
            control.wait_if_paused()

        log(f"{symbol} {entry_tf} Running...")
        direct_queue = _DirectCallbackQueue(
            lambda msg, _s=symbol: _emit_progress(_s, msg.get("stage"), msg.get("bar_pct"), msg.get("trades_so_far"))
        )
        try:
            result = run_one_symbol(config_dict, exchange, symbol, settings, start_ms, end_ms, batch_id, direct_queue)
            _save_and_report(symbol, result)
            done_count += 1
            _emit_progress(symbol, "completed", trades_so_far=len(result.get("trades") or []))
        except Exception as e:
            _save_and_report(symbol, None, error=e)
            done_count += 1
            _emit_progress(symbol, "failed")

    if control and control.should_stop():
        storage.update_batch_status(batch_id, "stopped", _now_iso())
    else:
        storage.update_batch_status(batch_id, "completed", _now_iso())
        log("Saving Results...")
        log("Backtest batch complete.")

    return batch_id
