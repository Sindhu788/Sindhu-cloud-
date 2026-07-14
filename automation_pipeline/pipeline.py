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


def trigger_pipeline_for_strategy(strategy_id, strategy_name=None, symbols=None):
    """Starts the pipeline as a background "pipeline" job and returns
    immediately, exactly like job_manager.create_job("backtest", ...) in
    sindhu_web/api/backtesting.py. Skips (rather than queues) if a
    pipeline or a manual backtest is already running, since both compete
    for the same multiprocessing worker pool -- consistent with the
    existing one-backtest-at-a-time rule, just extended to this new job
    kind. Never raises: a skip is logged and returned as None, so an
    import request is never blocked or failed by this.

    `symbols`: optional explicit coin list, overriding the normal "every
    downloaded coin for this exchange" default. Every real auto-trigger
    (import/clarification) always passes None -- this exists purely so a
    manual verification run (see /api/automation/trigger) can exercise the
    full backtest -> optimize -> re-backtest -> compare -> paper-trading
    chain quickly against a handful of coins instead of waiting on the
    full universe, without touching the production auto-trigger behavior
    at all."""
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
        return run_pipeline(job_id, strategy_id, control, symbols=symbols)

    job_manager.create_job("pipeline", _target, control=control, job_id=job_id)
    sync.notify("automation_pipeline", "started",
                f"Automation pipeline started for '{strategy_name or strategy_id}'", job_id=job_id)
    return job_id


def run_pipeline(job_id, strategy_id, control=None, symbols=None):
    """Part 4 (plain-language live logs + reliability): every log_fn() call
    below is written for a non-programmer reading the Live Logs panel in
    real time, not as an internal debug trace -- it says what SINDHU is
    doing and why, in plain English, at every stage from import through
    Paper Trading. `[automation-pipeline]` is kept as a prefix purely so
    these lines are easy to filter/grep in the log file; it's not meant to
    read as jargon on its own.

    Reliability: `control.should_stop()` is checked between every stage
    (not just inside runner.run_mtf_batch's own per-coin loop) so hitting
    Stop on this job halts it promptly at a clean boundary instead of
    powering through the remaining stages regardless."""
    log_fn = job_manager.make_log_fn(job_id)

    def _stage(stage, **extra):
        job_manager.update_progress(job_id, current_stage=stage, **extra)

    def _say(msg):
        log_fn(f"[automation-pipeline] {msg}")

    def _stopped(after_stage):
        _say(f"Stopped by request after the {after_stage} stage -- nothing further was started.")
        _stage("stopped", reason=after_stage)
        return {"error": "stopped", "stopped_after": after_stage}

    try:
        cfg = lib.load(strategy_id)
    except FileNotFoundError:
        _say(f"Could not find strategy {strategy_id} -- stopping here.")
        _stage("aborted", reason="strategy_not_found")
        return {"error": "strategy not found"}

    if validate(cfg):
        _say(f"'{cfg.name}' still has unresolved issues and isn't ready to backtest -- stopping here. "
             f"Resolve them from the Strategies page (Clarify) and it will run automatically once ready.")
        _stage("aborted", reason="not_ready")
        return {"error": "strategy not ready"}

    exchange = _default_exchange()
    symbols = symbols or storage.load_symbols(exchange)
    if not symbols:
        _say("No coin price data is available yet for this exchange -- stopping here. "
             "Download data from the Data page first.")
        _stage("aborted", reason="no_symbols")
        return {"error": "no symbols"}

    settings = {
        "initial_balance": 1000.0, "risk_pct": cfg.risk_pct or 1.0,
        "commission_pct": 0.1, "slippage_pct": 0.05, "position_size_pct": 10.0,
        "start_ms": None, "end_ms": None,
    }

    # ---------------------------------------------------------- Stage 1/4: backtesting
    _stage("backtesting", current_strategy=cfg.name, stage_label="Running the strategy against historical price data")
    _say(f"Step 1 of 4 -- Backtesting: testing '{cfg.name}' against real historical price data for "
         f"{len(symbols)} coins, to see how it would actually have performed.")

    def _progress_cb(done, total, symbol, timeframe, stage=None, bar_pct=None, trades_so_far=None, eta_seconds=None):
        job_manager.update_progress(
            job_id, current_stage="backtesting", done=done, total=total,
            current_coin=symbol, current_timeframe=timeframe, current_strategy=cfg.name,
            backtest_stage=stage, bar_pct=bar_pct, trades_so_far=trades_so_far, eta_seconds=eta_seconds,
            stage_label="Running the strategy against historical price data",
        )

    original_batch_id = runner.run_mtf_batch(
        cfg, exchange, symbols, settings, log=log_fn, control=control,
        progress_cb=_progress_cb, use_multiprocessing=True,
    )
    generate_report(original_batch_id)
    original_summary = quick_batch_summary(original_batch_id) or {}
    _say(f"Backtest finished: {original_summary.get('total_trades', 0)} trades, "
         f"{original_summary.get('win_rate', 0)}% win rate, "
         f"total profit/loss {original_summary.get('total_pnl')}.")

    if control and control.should_stop():
        return _stopped("backtesting")

    # ---------------------------------------------------------- Stage 2/4: optimizing
    optimizer_total = {"n": 0}

    def _opt_progress(tried_so_far, total_candidates):
        optimizer_total["n"] = total_candidates
        job_manager.update_progress(
            job_id, current_stage="optimizing", optimizer_tried=tried_so_far, optimizer_total=total_candidates,
            stage_label="Testing different settings to find the best version of this strategy",
        )

    _stage("optimizing", stage_label="Testing different settings to find the best version of this strategy")
    _say("Step 2 of 4 -- Finding better settings: trying different combinations of this strategy's own "
         "numeric settings (things like lookback windows, stop-loss size, risk per trade, session "
         "filters) to see if any version performs better. This is pure math/combinatorics -- no AI "
         "provider is called and no AI tokens are used for this step.")
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - FAST_SCREEN_WINDOW_DAYS * 24 * 3600 * 1000
    screen_symbol = symbols[0]
    _say(f"To keep this quick, each combination is first tried on just {screen_symbol}'s last "
         f"{FAST_SCREEN_WINDOW_DAYS} days (no data is saved during this quick-test pass) -- "
         f"only the single best combination goes on to a full, real test next.")

    def _opt_log(msg):
        _say(msg)

    best_candidate, tried, best_desc = optimizer.optimize(
        cfg, exchange, screen_symbol, dict(settings), start_ms, end_ms,
        log_fn=_opt_log, control=control, progress_cb=_opt_progress,
    )

    if control and control.should_stop():
        return _stopped("optimizing")

    optimized_batch_id = None
    optimized_summary = None
    winner = "original"

    if best_candidate is not None:
        _stage("optimizing", validating_candidate=best_desc,
               stage_label="Double-checking the best combination on the full history")
        _say(f"Found a promising combination ({best_desc}). Now running a REAL, full backtest with it "
             f"-- same {len(symbols)} coins and the same full date range as the original -- to make "
             f"sure it's a genuine improvement and not just a lucky result on the small quick-test sample.")

        def _val_progress_cb(done, total, symbol, timeframe, stage=None, bar_pct=None, trades_so_far=None, eta_seconds=None):
            job_manager.update_progress(
                job_id, current_stage="optimizing", done=done, total=total,
                current_coin=symbol, current_timeframe=timeframe,
                current_strategy=f"{cfg.name} (optimized candidate)",
                backtest_stage=stage, bar_pct=bar_pct, trades_so_far=trades_so_far, eta_seconds=eta_seconds,
                stage_label="Double-checking the best combination on the full history",
            )

        optimized_batch_id = runner.run_mtf_batch(
            best_candidate, exchange, symbols, settings, log=log_fn, control=control,
            progress_cb=_val_progress_cb, use_multiprocessing=True,
        )
        generate_report(optimized_batch_id)
        optimized_summary = quick_batch_summary(optimized_batch_id) or {}
        _say(f"Full test of the optimized version finished: {optimized_summary.get('total_trades', 0)} trades, "
             f"{optimized_summary.get('win_rate', 0)}% win rate, "
             f"total profit/loss {optimized_summary.get('total_pnl')}.")

        orig_pnl = original_summary.get("total_pnl")
        opt_pnl = optimized_summary.get("total_pnl")
        if opt_pnl is not None and (orig_pnl is None or opt_pnl > orig_pnl):
            winner = "optimized"
        _say(f"Result: the {winner.upper()} version performed better "
             f"(original: {orig_pnl}, optimized: {opt_pnl}).")
    else:
        _say("None of the combinations tried beat the original on the quick test, so the optimized "
             "version is skipped -- no need to spend time on a full test that won't win anyway. "
             "Keeping the strategy exactly as imported.")

    if control and control.should_stop():
        return _stopped("optimizing")

    # ---------------------------------------------------------- Stage 3/4: comparing
    _stage("comparing", winner=winner, stage_label="Saving the original vs optimized comparison")
    opt_id = uuid.uuid4().hex[:12]
    params_changed = [{"description": best_desc}] if (winner == "optimized" and best_desc) else []
    storage.save_optimization(
        opt_id, strategy_id, original_batch_id, optimized_batch_id, winner,
        params_changed, tried, _now_iso(),
    )
    _say(f"Step 3 of 4 -- Saving the comparison: you can see the original vs optimized side by side "
         f"any time in Backtest History (winner: {winner}).")

    # If the optimized candidate won, persist it as a new version of the
    # SAME saved strategy -- strategy_library.load(strategy_id) always
    # returns the current version, so Paper Trading (below) picks up the
    # winning parameters automatically with no export/import step.
    if winner == "optimized" and best_candidate is not None:
        best_candidate.name = cfg.name
        lib.save_version(strategy_id, best_candidate)
        _say(f"Saved the optimized settings as the new version of '{cfg.name}' -- "
             f"nothing to export or re-import.")

    if control and control.should_stop():
        return _stopped("comparing")

    # ---------------------------------------------------------- Stage 4/4: paper trading handoff
    _stage("starting_paper_trading", winner=winner, stage_label="Starting Paper Trading with the winning version")
    _say(f"Step 4 of 4 -- Starting Paper Trading: handing the {winner.upper()} version of '{cfg.name}' "
         f"to Paper Trading so SINDHU can start trading it live (simulated) automatically.")

    from paper_trading.engine import engine as pt_engine
    from sindhu_web.api.paper_trading import _log_and_broadcast, _on_engine_event

    if pt_engine.is_running():
        _say("Paper Trading was already running with a different setup -- restarting it scoped to just this strategy.")
        pt_engine.stop()
        waited = 0.0
        while pt_engine.is_running() and waited < 15.0:
            time.sleep(0.5)
            waited += 0.5

    started = pt_engine.start(log=_log_and_broadcast, on_event=_on_engine_event, only_strategy_id=strategy_id)
    if started:
        _say(f"Done -- Paper Trading is now running '{cfg.name}' live (simulated), and only this strategy.")
    else:
        _say("Could not start Paper Trading (it reported it was still busy shutting down) -- "
             "you can start it manually from the Paper Trading page.")

    _stage("completed", winner=winner, paper_trading_started=started,
           stage_label="Done -- see the results in Backtest History")
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
