"""The auto backtest -> optimize -> compare -> paper-trading pipeline
(Part 2). Triggered automatically the moment a strategy import saves
something Backtesting Ready -- see the hook points in
ai_integration/importer.py::import_document() and
knowledge_compiler/compiler.py::compile_document(), which both call
trigger_pipeline_for_strategy() below. The CEO never has to load the
Backtesting page or click "Run Backtest" manually for this to happen.

Reuses the exact same job_manager pattern already used for kind="backtest"
jobs (sindhu_web/api/backtesting.py) -- a new kind="pipeline" job, running
in its own background thread, reporting progress via
job_manager.update_progress(job_id, current_stage=...) exactly like the
existing backtest progress wiring, so the same WebSocket/broadcast/
/api/jobs plumbing works unmodified."""

import time
import uuid
from datetime import datetime, timezone

from backtest_engine import runner, strategy_library as lib
from backtest_engine.reports import generate_report, quick_batch_summary
from backtest_engine.validator import validate
from data_engine import storage, config as base_config
from data_engine.control import DownloadControl
from data_engine.logging_setup import log as file_log
from sindhu_web.jobs import job_manager
from sindhu_web import sync

from automation_pipeline import optimizer

FAST_SCREEN_WINDOW_DAYS = 30


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _default_exchange():
    cfg = base_config.load_or_seed("exchanges.json", base_config.DEFAULTS["exchanges.json"])
    return cfg["default"]


def trigger_pipeline_for_strategy(strategy_id, strategy_name=None):
    """Starts the pipeline as a background "pipeline" job and returns
    immediately, exactly like job_manager.create_job("backtest", ...) in
    sindhu_web/api/backtesting.py. Skips (rather than queues) if a
    pipeline or a manual backtest is already running, since both compete
    for the same multiprocessing worker pool -- consistent with the
    existing one-backtest-at-a-time rule, just extended to this new job
    kind. Never raises: a skip is logged and returned as None, so an
    import request is never blocked or failed by this."""
    if job_manager.get_running_job_of_kind("pipeline") is not None:
        file_log(f"[automation-pipeline] Skipped auto-pipeline for '{strategy_name or strategy_id}' "
                  f"-- another pipeline is already running.")
        return None
    if job_manager.get_running_job_of_kind("backtest") is not None:
        file_log(f"[automation-pipeline] Skipped auto-pipeline for '{strategy_name or strategy_id}' "
                  f"-- a manual backtest is already running.")
        return None

    job_id = uuid.uuid4().hex[:12]
    control = DownloadControl()

    def _target():
        return run_pipeline(job_id, strategy_id, control)

    job_manager.create_job("pipeline", _target, control=control, job_id=job_id)
    sync.notify("automation_pipeline", "started",
                f"Automation pipeline started for '{strategy_name or strategy_id}'", job_id=job_id)
    return job_id


def run_pipeline(job_id, strategy_id, control=None):
    log_fn = job_manager.make_log_fn(job_id)

    def _stage(stage, **extra):
        job_manager.update_progress(job_id, current_stage=stage, **extra)

    try:
        cfg = lib.load(strategy_id)
    except FileNotFoundError:
        log_fn(f"[automation-pipeline] Strategy {strategy_id} not found -- aborting.")
        _stage("aborted", reason="strategy_not_found")
        return {"error": "strategy not found"}

    if validate(cfg):
        log_fn(f"[automation-pipeline] '{cfg.name}' is not Backtesting Ready -- aborting pipeline.")
        _stage("aborted", reason="not_ready")
        return {"error": "strategy not ready"}

    exchange = _default_exchange()
    symbols = storage.load_symbols(exchange)
    if not symbols:
        log_fn("[automation-pipeline] No coins available for this exchange -- aborting.")
        _stage("aborted", reason="no_symbols")
        return {"error": "no symbols"}

    settings = {
        "initial_balance": 1000.0, "risk_pct": cfg.risk_pct or 1.0,
        "commission_pct": 0.1, "slippage_pct": 0.05, "position_size_pct": 10.0,
        "start_ms": None, "end_ms": None,
    }

    # ---------------------------------------------------------- Stage 1/4: backtesting
    _stage("backtesting", current_strategy=cfg.name)
    log_fn(f"[automation-pipeline] Stage 1/4 (backtesting): running the original backtest for "
           f"'{cfg.name}' across {len(symbols)} coins...")

    def _progress_cb(done, total, symbol, timeframe, stage=None, bar_pct=None, trades_so_far=None, eta_seconds=None):
        job_manager.update_progress(
            job_id, current_stage="backtesting", done=done, total=total,
            current_coin=symbol, current_timeframe=timeframe, current_strategy=cfg.name,
            backtest_stage=stage, bar_pct=bar_pct, trades_so_far=trades_so_far, eta_seconds=eta_seconds,
        )

    original_batch_id = runner.run_mtf_batch(
        cfg, exchange, symbols, settings, log=log_fn, control=control,
        progress_cb=_progress_cb, use_multiprocessing=True,
    )
    generate_report(original_batch_id)
    original_summary = quick_batch_summary(original_batch_id) or {}
    log_fn(f"[automation-pipeline] Original backtest complete: batch {original_batch_id}, "
           f"{original_summary.get('total_trades', 0)} trades, {original_summary.get('win_rate', 0)}% win rate, "
           f"PnL {original_summary.get('total_pnl')}.")

    # ---------------------------------------------------------- Stage 2/4: optimizing
    _stage("optimizing")
    log_fn("[automation-pipeline] Stage 2/4 (optimizing): running the math-based optimizer -- "
           "pure grid search over this strategy's own tunable parameters, no AI provider is called.")
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - FAST_SCREEN_WINDOW_DAYS * 24 * 3600 * 1000
    screen_symbol = symbols[0]
    log_fn(f"[automation-pipeline] Fast screen uses {screen_symbol} over the last "
           f"{FAST_SCREEN_WINDOW_DAYS} days (in-memory, no database writes).")

    def _opt_log(msg):
        log_fn(f"[automation-pipeline] {msg}")
        job_manager.update_progress(job_id, current_stage="optimizing", last_optimizer_log=msg)

    best_candidate, tried, best_desc = optimizer.optimize(
        cfg, exchange, screen_symbol, dict(settings), start_ms, end_ms, log_fn=_opt_log,
    )

    optimized_batch_id = None
    optimized_summary = None
    winner = "original"

    if best_candidate is not None:
        _stage("optimizing", validating_candidate=best_desc)
        log_fn(f"[automation-pipeline] Validating best candidate ({best_desc}) on the FULL dataset "
               f"({len(symbols)} coins, same range as the original backtest) to confirm it isn't "
               f"overfit to the fast subset...")

        def _val_progress_cb(done, total, symbol, timeframe, stage=None, bar_pct=None, trades_so_far=None, eta_seconds=None):
            job_manager.update_progress(
                job_id, current_stage="optimizing", done=done, total=total,
                current_coin=symbol, current_timeframe=timeframe,
                current_strategy=f"{cfg.name} (optimized candidate)",
                backtest_stage=stage, bar_pct=bar_pct, trades_so_far=trades_so_far, eta_seconds=eta_seconds,
            )

        optimized_batch_id = runner.run_mtf_batch(
            best_candidate, exchange, symbols, settings, log=log_fn, control=control,
            progress_cb=_val_progress_cb, use_multiprocessing=True,
        )
        generate_report(optimized_batch_id)
        optimized_summary = quick_batch_summary(optimized_batch_id) or {}
        log_fn(f"[automation-pipeline] Optimized candidate full-dataset result: batch {optimized_batch_id}, "
               f"{optimized_summary.get('total_trades', 0)} trades, {optimized_summary.get('win_rate', 0)}% win rate, "
               f"PnL {optimized_summary.get('total_pnl')}.")

        orig_pnl = original_summary.get("total_pnl")
        opt_pnl = optimized_summary.get("total_pnl")
        if opt_pnl is not None and (orig_pnl is None or opt_pnl > orig_pnl):
            winner = "optimized"
        log_fn(f"[automation-pipeline] Winner: {winner} (original PnL {orig_pnl}, optimized PnL {opt_pnl}).")
    else:
        log_fn("[automation-pipeline] Optimizer found no improving candidate on the fast subset -- "
               "keeping the original strategy, no full-dataset validation run needed.")

    # ---------------------------------------------------------- Stage 3/4: comparing
    _stage("comparing", winner=winner)
    opt_id = uuid.uuid4().hex[:12]
    params_changed = [{"description": best_desc}] if (winner == "optimized" and best_desc) else []
    storage.save_optimization(
        opt_id, strategy_id, original_batch_id, optimized_batch_id, winner,
        params_changed, tried, _now_iso(),
    )
    log_fn(f"[automation-pipeline] Stage 3/4 (comparing): saved comparison record {opt_id} "
           f"(original={original_batch_id}, optimized={optimized_batch_id}, winner={winner}).")

    # If the optimized candidate won, persist it as a new version of the
    # SAME saved strategy -- strategy_library.load(strategy_id) always
    # returns the current version, so Paper Trading (below) picks up the
    # winning parameters automatically with no export/import step.
    if winner == "optimized" and best_candidate is not None:
        best_candidate.name = cfg.name
        lib.save_version(strategy_id, best_candidate)
        log_fn(f"[automation-pipeline] Saved the optimized parameters as a new version of '{cfg.name}'.")

    # ---------------------------------------------------------- Stage 4/4: paper trading handoff
    _stage("starting_paper_trading", winner=winner)
    log_fn(f"[automation-pipeline] Stage 4/4 (starting_paper_trading): starting Paper Trading with the "
           f"{winner} version of '{cfg.name}'...")

    from paper_trading.engine import engine as pt_engine
    from sindhu_web.api.paper_trading import _log_and_broadcast, _on_engine_event

    if pt_engine.is_running():
        log_fn("[automation-pipeline] Paper Trading was already running -- restopping it scoped to this strategy.")
        pt_engine.stop()
        waited = 0.0
        while pt_engine.is_running() and waited < 15.0:
            time.sleep(0.5)
            waited += 0.5

    started = pt_engine.start(log=_log_and_broadcast, on_event=_on_engine_event, only_strategy_id=strategy_id)
    if started:
        log_fn(f"[automation-pipeline] Paper Trading is now running, scoped to '{cfg.name}' only.")
    else:
        log_fn("[automation-pipeline] Could not start Paper Trading (engine reported still busy stopping).")

    _stage("completed", winner=winner, paper_trading_started=started)
    sync.notify(
        "automation_pipeline", "finished",
        f"Automation pipeline finished for '{cfg.name}': winner={winner}, "
        f"Paper Trading {'started' if started else 'NOT started'}.",
        job_id=job_id,
    )

    return {
        # job_manager.create_job's finished-event broadcast reads
        # job.result["batch_id"] specifically (see sindhu_web/jobs/
        # job_manager.py) -- the same convention the "backtest" job kind
        # uses, so the frontend's existing "View Results" toast action
        # works unmodified for pipeline jobs too.
        "batch_id": optimized_batch_id or original_batch_id,
        "strategy_id": strategy_id, "original_batch_id": original_batch_id,
        "optimized_batch_id": optimized_batch_id, "winner": winner,
        "paper_trading_started": started,
    }
