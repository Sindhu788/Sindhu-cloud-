"""Module-level worker function for running one symbol's multi-timeframe
backtest -- kept top-level (not a closure/method) so it's picklable and can
run in a separate process via ProcessPoolExecutor.

progress_queue (Phase 6) is anything with a `.put(dict)` method -- a real
multiprocessing.Manager().Queue() proxy when this runs in a worker process,
or a lightweight direct-callback adapter (see runner._DirectCallbackQueue)
when it runs sequentially in the main process. Either way this function's
own code is identical, and it's always optional (None = no progress
reporting, unchanged from before Phase 6).

v8 (Debug Mode): the stage checklist below is deliberately named to match
what an operator actually needs to see happen, in order -- strategy_loaded
-> strategy_compiled -> timeframes_detected -> historical_data_loading ->
timeframes_resampled -> timeframes_synchronized -> indicators_initialized
-> rules_loaded -> simulating_bars -> trades_executed -> results_generated
-> completed. This extends the existing progress_queue mechanism (no new
system); a failure now always carries {stage, function, reason,
suggested_fix} instead of a bare string, and the whole function is wrapped
so an unexpected exception is reported the same structured way rather than
propagating as a raw traceback."""


import queue as _queue_mod
import threading as _threading_mod

# Per-process (each ProcessPoolExecutor worker imports this module fresh, so
# these globals are naturally isolated per worker) local relay: _emit() below
# must NEVER block the simulation loop, but the real progress_queue is a
# multiprocessing.Manager().Queue() proxy whose .put() can stall if the
# manager/consumer side is slow or stuck. So _emit() only ever touches this
# bounded, in-process queue.Queue (put_nowait -- raises/drops instead of
# blocking), while a single background thread relays from it to the real
# cross-process queue. If that relay thread ever gets stuck on the real
# queue's .put(), messages simply pile up here until the bound is hit and
# start being dropped -- the worker/simulation itself never waits on it.
_relay_queue = None
_relay_thread = None
_relay_lock = _threading_mod.Lock()


def _relay_loop(progress_queue):
    while True:
        msg = _relay_queue.get()
        if msg is None:
            return
        try:
            progress_queue.put(msg)
        except Exception:
            pass


def _ensure_relay(progress_queue):
    global _relay_queue, _relay_thread
    with _relay_lock:
        if _relay_queue is None:
            _relay_queue = _queue_mod.Queue(maxsize=2000)
            _relay_thread = _threading_mod.Thread(target=_relay_loop, args=(progress_queue,), daemon=True)
            _relay_thread.start()


def _emit(progress_queue, symbol, stage, **extra):
    if progress_queue is None:
        return
    try:
        _ensure_relay(progress_queue)
        _relay_queue.put_nowait({"symbol": symbol, "stage": stage, **extra})
    except Exception:
        pass


def _failure(stage, function, reason, suggested_fix):
    return {
        "status": "error",
        "stage": stage, "function": function, "reason": reason, "suggested_fix": suggested_fix,
        "error": f"[{stage}] {reason}",  # kept for any older caller that only reads "error"
        "trades": [], "metrics": None, "condition_report": None,
    }


def run_one_symbol(config_dict, exchange, symbol, settings, start_ms, end_ms, batch_id=None, progress_queue=None):
    from backtest_engine.strategy_config import StrategyConfig
    from backtest_engine.configured_strategy import ConfiguredStrategy
    from backtest_engine.mtf_context import MultiTimeframeContext
    from backtest_engine import engine, diagnostics
    from backtest_engine.metrics import compute_metrics
    from knowledge_engine.engine import KnowledgeEngine

    stage = "strategy_loaded"
    ke = None
    try:
        config = StrategyConfig.from_dict(config_dict)
        _emit(progress_queue, symbol, stage)

        stage = "strategy_compiled"
        strategy = ConfiguredStrategy(config)
        _emit(progress_queue, symbol, stage)

        stage = "timeframes_detected"
        if "entry" not in config.timeframes:
            return _failure(
                stage, "run_one_symbol",
                "No entry timeframe was found in the compiled strategy.",
                "Re-import the strategy, or set an entry timeframe manually before backtesting.",
            )
        _emit(progress_queue, symbol, stage, timeframes=config.timeframes)

        stage = "historical_data_loading"
        ctx = MultiTimeframeContext(exchange, symbol, config.timeframes, start_ms, end_ms)
        if ctx.is_empty():
            return _failure(
                stage, "MultiTimeframeContext",
                f"No 1-minute candle data is available for {symbol} on {exchange} in the requested date range.",
                f"Download historical data for {symbol} on {exchange} first (Data page), then re-run this backtest.",
            )
        _emit(progress_queue, symbol, stage)

        # Every non-1m role's frame was already resampled on the fly from
        # the 1m source of truth inside MultiTimeframeContext.__init__ (via
        # data_engine.resample.get_ohlcv) -- this never fails from a
        # "missing timeframe" as long as 1m data exists, so by this point
        # resampling has already unconditionally happened.
        _emit(progress_queue, symbol, "timeframes_resampled")

        stage = "indicators_initialized"
        merged = strategy.prepare_context(ctx)  # also synchronizes timeframes (ctx.build()) internally
        _emit(progress_queue, symbol, "timeframes_synchronized")
        _emit(progress_queue, symbol, stage)

        stage = "rules_loaded"
        entry_tf = config.timeframes.get("entry", "?")
        # A strategy using separate Long/Short entry rule sets satisfies
        # "has entry rules" via EITHER of those instead of entry_conditions
        # -- same check as validator.py and ConfiguredStrategy.on_bar().
        if not config.entry_conditions and not (config.long_entry_conditions or config.short_entry_conditions):
            return _failure(
                stage, "run_one_symbol",
                "The compiled strategy has no entry conditions to evaluate.",
                "Re-import the strategy so it includes at least one entry rule.",
            )
        # Every backtest automatically applies whatever active lessons exist
        # -- if there are none, this is a harmless no-op (engine.py only
        # checks when knowledge_engine.has_active_lessons() would matter,
        # and an empty lesson list simply never blocks anything).
        ke = KnowledgeEngine.for_backtesting(batch_id=batch_id, symbol=symbol, timeframe=entry_tf)
        _emit(progress_queue, symbol, stage)

        def _bar_cb(i, n, trades_so_far):
            _emit(progress_queue, symbol, "simulating_bars",
                  bar_pct=round(i / n * 100, 1) if n else 100.0, trades_so_far=trades_so_far)

        stage = "simulating_bars"
        _emit(progress_queue, symbol, stage, bar_pct=0.0, trades_so_far=0)
        trades, equity_curve, _final_balance = engine.run_backtest(
            merged, strategy, settings, knowledge_engine=ke, bar_progress_cb=_bar_cb,
        )
        ke.flush()  # one bulk write for the whole run instead of one per bar
        _emit(progress_queue, symbol, "trades_executed", trades_so_far=len(trades))

        stage = "results_generated"
        metrics = compute_metrics(trades, equity_curve, settings["initial_balance"])

        condition_report = None
        if not trades:
            try:
                condition_report = diagnostics.condition_hit_report(config, merged)
            except Exception:
                condition_report = None
        _emit(progress_queue, symbol, stage)

        _emit(progress_queue, symbol, "completed", trades_so_far=len(trades))
        return {"status": "completed", "trades": trades, "metrics": metrics, "condition_report": condition_report}
    except Exception as exc:  # pragma: no cover -- must never surface as a raw traceback to the CEO
        if ke is not None:
            try:
                ke.flush()  # don't lose already-buffered lesson stats from a partial run
            except Exception:
                pass
        _emit(progress_queue, symbol, "failed", failed_at_stage=stage, reason=str(exc))
        return _failure(
            stage, "run_one_symbol",
            f"Unexpected error: {exc}",
            "Check the strategy configuration and the exchange/symbol/date range for this backtest.",
        )
