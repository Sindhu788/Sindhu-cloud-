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
from backtest_engine.strategy_config import StrategyConfig
from backtest_engine.validator import validate
from backtest_engine import sanity_check
from data_engine import storage, config as base_config
from data_engine.control import DownloadControl
from data_engine.logging_setup import log as file_log
from sindhu_web.jobs import job_manager
from sindhu_web import sync

from automation_pipeline import optimizer
from automation_pipeline import walk_forward
from ai_integration import extraction_lock

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
    # Batch 3, Task 3: Incomplete Lock -- a strategy with rules the
    # system still couldn't understand (after Task 2's retries) never
    # enters backtesting/optimization/paper-trading via the automatic
    # pipeline, unless the CEO already explicitly overrode it. Skipped
    # (not raised) for the same reason the concurrent-job checks below
    # are skips -- an import request must never fail because of this.
    lock_status = extraction_lock.check_strategy_lock(strategy_id)
    if lock_status["locked"]:
        file_log(f"[automation-pipeline] Skipped auto-pipeline for '{strategy_name or strategy_id}' -- "
                  f"{extraction_lock.lock_message(lock_status)}")
        return None

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
    # Durable row -- exists in the database from this point on, independent
    # of job_manager's in-memory Job (which is lost on restart). If the
    # server dies before this INSERT even happens, there's nothing to
    # resume, which is the same as the trigger never having occurred --
    # the safest possible outcome for that edge case.
    storage.create_pipeline_job(job_id, strategy_id, strategy_name, symbols, _now_iso())

    def _target():
        return run_pipeline(job_id, strategy_id, control, symbols=symbols)

    job_manager.create_job("pipeline", _target, control=control, job_id=job_id)
    sync.notify("automation_pipeline", "started",
                f"Automation pipeline started for '{strategy_name or strategy_id}'", job_id=job_id)
    return job_id


def resume_pipeline_jobs_on_startup():
    """Called once during server startup (see sindhu_web/server.py's
    lifespan). job_manager's in-memory Job registry is always empty right
    after a restart -- any pipeline_jobs row still marked 'running' can only
    mean the server stopped (crash, power loss, forceful kill) while that
    pipeline was actually in progress, since every normal exit path already
    sets a terminal status before returning. For each such row: reconnect it
    to a live job_manager job and continue from its last durable checkpoint
    (using the SAME job_id, so it's the same continuous entry in Backtest
    History / Recent Activity, not a new one), unless the strategy it
    depended on no longer exists -- that's the one case with nothing left
    to resume, so it's marked failed instead.

    Never raises: a problem resuming one job must never prevent the server
    from starting or block resuming the others."""
    stale = storage.list_running_pipeline_jobs()
    if not stale:
        return
    file_log(f"[automation-pipeline] Found {len(stale)} pipeline job(s) still marked 'running' from before "
              f"the last restart -- the server must have stopped unexpectedly while they were in progress.")

    # Only one pipeline is ever supposed to run at a time (enforced in
    # trigger_pipeline_for_strategy), so under normal operation this list
    # has at most one row. If more than one somehow got left 'running'
    # (e.g. two separate crashes before either finished), only the single
    # most recent is actually resumed -- the rest are marked failed rather
    # than started concurrently, which would silently break that rule.
    stale.sort(key=lambda r: r["updated_at"], reverse=True)
    to_resume, to_fail = stale[0], stale[1:]

    for row in to_fail:
        file_log(f"[automation-pipeline] Job {row['job_id']} for '{row['strategy_name']}' was also left "
                 f"'running' -- only the most recent interrupted job is resumed, so this one is marked failed.")
        storage.update_pipeline_job(
            row["job_id"], _now_iso(), status="failed",
            error="superseded by a more recent interrupted job; only one pipeline resumes at a time",
        )

    try:
        _resume_one_pipeline_job(to_resume)
    except Exception as exc:  # pragma: no cover -- must never take down startup
        job_id = to_resume["job_id"]
        file_log(f"[automation-pipeline] Could not resume job {job_id}: {exc!r} -- marking it failed.")
        try:
            storage.update_pipeline_job(job_id, _now_iso(), status="failed", error=f"resume failed: {exc!r}")
        except Exception:
            pass


def _resume_one_pipeline_job(row):
    job_id = row["job_id"]
    strategy_id = row["strategy_id"]
    strategy_name = row["strategy_name"] or strategy_id
    stage = row["stage"] or "sanity_check"

    try:
        lib.load(strategy_id)
    except FileNotFoundError:
        file_log(f"[automation-pipeline] Job {job_id} for '{strategy_name}' was interrupted at the "
                 f"'{stage}' stage, but the strategy no longer exists -- marking failed, nothing to resume.")
        storage.update_pipeline_job(
            job_id, _now_iso(), status="failed",
            error=f"strategy {strategy_id} no longer exists; interrupted at stage '{stage}'",
        )
        sync.notify("automation_pipeline", "failed",
                     f"Previous pipeline run for '{strategy_name}' was interrupted at the '{stage}' stage and "
                     f"cannot be resumed (the strategy was deleted) -- marked failed, ready for a fresh start.",
                     job_id=job_id)
        return

    file_log(f"[automation-pipeline] Resuming job {job_id} for '{strategy_name}' -- it was interrupted at "
             f"the '{stage}' stage.")
    sync.notify("automation_pipeline", "resumed",
                f"Resuming pipeline for '{strategy_name}' from the '{stage}' stage (job {job_id}) -- "
                f"the server was interrupted mid-run and has now recovered.",
                job_id=job_id)

    control = DownloadControl()

    def _target():
        return run_pipeline(job_id, strategy_id, control, symbols=row["symbols"], resume=row)

    # Reuses the SAME job_id job_manager-side too, so /api/jobs, Backtest
    # History, and the Live Log panel all show one continuous timeline
    # across the restart instead of a orphaned "stuck running" entry plus a
    # brand new unrelated one.
    job_manager.create_job("pipeline", _target, control=control, job_id=job_id)


def run_pipeline(job_id, strategy_id, control=None, symbols=None, resume=None):
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
    powering through the remaining stages regardless.

    Interruption/resume (`resume`, from resume_pipeline_jobs_on_startup()):
    `resume["checkpoint"]` carries whatever was safely persisted before the
    server last stopped. Two kinds of stage in this pipeline behave
    differently on resume:
    - backtesting (the original run AND the optimizer's full validation of
      its winning candidate) is durably resumable per-coin -- runner.
      run_mtf_batch() already skips any (symbol, timeframe) already marked
      'completed' for a given batch_id, so passing the SAME batch_id back in
      continues exactly where the interrupted run left off, never re-running
      finished coins.
    - the optimizer's quick-screen scan deliberately saves nothing (it's
      designed to be fast and disposable -- see optimizer.py), so there is
      no partial progress to trust; if interrupted there, that stage simply
      restarts from its first candidate. This never repeats the (already
      persisted, already-verified) backtesting stage, only the screen
      itself, so nothing expensive is redone."""
    log_fn = job_manager.make_log_fn(job_id)
    is_resuming = resume is not None
    checkpoint = dict(resume["checkpoint"]) if resume else {}

    def _stage(stage, **extra):
        job_manager.update_progress(job_id, current_stage=stage, **extra)

    def _say(msg):
        log_fn(f"[automation-pipeline] {msg}")

    def _checkpoint(stage, **updates):
        """Persists the durable resume state. Always writes the FULL
        current checkpoint dict (never a partial merge), so a read after
        this call is always self-consistent even if the process dies the
        instant after this line runs."""
        checkpoint.update(updates)
        storage.update_pipeline_job(job_id, _now_iso(), stage=stage, checkpoint=dict(checkpoint))

    def _fail(reason):
        storage.update_pipeline_job(job_id, _now_iso(), status="failed", error=reason)

    def _stopped(after_stage):
        _say(f"Stopped by request after the {after_stage} stage -- nothing further was started.")
        _stage("stopped", reason=after_stage)
        storage.update_pipeline_job(job_id, _now_iso(), status="stopped")
        return {"error": "stopped", "stopped_after": after_stage}

    # Batch 3, Task 3: if this strategy was previously locked and the CEO
    # explicitly overrode it, every batch this pipeline run produces is
    # permanently tagged -- resume_pipeline_jobs_on_startup() calls this
    # same function, so a resumed run stays tagged consistently too.
    lock_status = extraction_lock.check_strategy_lock(strategy_id)
    extraction_override_warning = lock_status["overridden"] and bool(lock_status["missing_rules"])

    try:
        try:
            cfg = lib.load(strategy_id)
        except FileNotFoundError:
            _say(f"Could not find strategy {strategy_id} -- stopping here.")
            _stage("aborted", reason="strategy_not_found")
            _fail("strategy not found")
            return {"error": "strategy not found"}

        if validate(cfg):
            _say(f"'{cfg.name}' still has unresolved issues and isn't ready to backtest -- stopping here. "
                 f"Resolve them from the Strategies page (Clarify) and it will run automatically once ready.")
            _stage("aborted", reason="not_ready")
            _fail("strategy not ready")
            return {"error": "strategy not ready"}

        exchange = _default_exchange()
        symbols = symbols or storage.load_symbols(exchange)
        if not symbols:
            _say("No coin price data is available yet for this exchange -- stopping here. "
                 "Download data from the Data page first.")
            _stage("aborted", reason="no_symbols")
            _fail("no symbols")
            return {"error": "no symbols"}

        settings = {
            "initial_balance": 1000.0, "risk_pct": cfg.risk_pct or 1.0,
            "commission_pct": 0.1, "slippage_pct": 0.05, "position_size_pct": 10.0,
            "start_ms": None, "end_ms": None,
        }

        if is_resuming:
            _say(f"Recovered after an interruption (the server stopped unexpectedly mid-run) -- resuming "
                 f"this pipeline for '{cfg.name}' (job {job_id}) from where it left off instead of starting "
                 f"over from scratch.")

        # Part 3: fast sanity check on a couple of coins / a short recent
        # window BEFORE committing to the full (potentially 50-coin)
        # backtest below -- catches a structural 0-trade strategy
        # immediately instead of after the whole pipeline has already run.
        # Skipped on resume once a batch_id has been checkpointed, since
        # that only happens after the sanity check already passed.
        if not checkpoint.get("original_batch_id"):
            _say(f"Sanity check: quickly testing '{cfg.name}' on a couple of coins over a short recent window "
                 f"before running the full backtest, to catch a broken strategy early.")
            sanity = sanity_check.run_sanity_check(cfg.to_dict(), exchange, symbols, settings)
            if not sanity["ok"]:
                _say(f"Sanity check failed: {sanity['reason']} {sanity['diagnosis'] or ''}".strip())
                _say(f"Stopping here -- fix '{cfg.name}' and it will run automatically once it passes.")
                _stage("aborted", reason="sanity_check_failed", sanity_check=sanity)
                _fail("sanity check failed")
                return {"error": "sanity check failed", "sanity_check": sanity}
            _say(f"Sanity check passed ({sanity['trades_found']} trade(s) found on "
                 f"{', '.join(sanity['symbols_checked'])}) -- proceeding to the full backtest.")
        else:
            _say("Sanity check already passed before the interruption -- not repeating it.")

        # ---------------------------------------------------------- Stage 1/4: backtesting
        if checkpoint.get("original_backtest_done"):
            original_batch_id = checkpoint["original_batch_id"]
            original_summary = checkpoint.get("original_summary") or {}
            _stage("backtesting", current_strategy=cfg.name, stage_label="Reusing the previously completed backtest")
            _say(f"Step 1 of 4 -- Backtesting: already completed before the interruption "
                 f"(batch {original_batch_id}: {original_summary.get('total_trades', 0)} trades, "
                 f"{original_summary.get('win_rate', 0)}% win rate) -- reusing it instead of re-running.")
        else:
            original_batch_id = checkpoint.get("original_batch_id") or runner.new_batch_id()
            _checkpoint("backtesting", original_batch_id=original_batch_id)
            _stage("backtesting", current_strategy=cfg.name, stage_label="Running the strategy against historical price data")
            if checkpoint.get("original_batch_id") and is_resuming:
                _say(f"Resuming Step 1 of 4 -- Backtesting: continuing batch {original_batch_id} for '{cfg.name}' -- "
                     f"coins already completed before the interruption are skipped, not redone.")
            else:
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
                progress_cb=_progress_cb, use_multiprocessing=True, batch_id=original_batch_id,
                extraction_override_warning=extraction_override_warning,
            )
            if control and control.should_stop():
                return _stopped("backtesting")

            generate_report(original_batch_id)
            original_summary = quick_batch_summary(original_batch_id) or {}
            _say(f"Backtest finished: {original_summary.get('total_trades', 0)} trades, "
                 f"{original_summary.get('win_rate', 0)}% win rate, "
                 f"total profit/loss {original_summary.get('total_pnl')}.")
            _checkpoint("optimizing", original_batch_id=original_batch_id,
                        original_backtest_done=True, original_summary=original_summary)

        # ---------------------------------------------------------- Stage 2/4: optimizing (quick screen)
        if checkpoint.get("optimizer_done"):
            best_candidate = StrategyConfig.from_dict(checkpoint["best_candidate"]) if checkpoint.get("best_candidate") else None
            best_desc = checkpoint.get("best_desc")
            tried = checkpoint.get("tried", 0)
            _say("Step 2 of 4 -- Finding better settings: already completed before the interruption "
                 + (f"(found: {best_desc})." if best_candidate else "(no combination beat the original).")
                 + " Reusing that result.")
        else:
            optimizer_total = {"n": 0}

            def _opt_progress(tried_so_far, total_candidates):
                optimizer_total["n"] = total_candidates
                job_manager.update_progress(
                    job_id, current_stage="optimizing", optimizer_tried=tried_so_far, optimizer_total=total_candidates,
                    stage_label="Testing different settings to find the best version of this strategy",
                )

            _stage("optimizing", stage_label="Testing different settings to find the best version of this strategy")
            if is_resuming:
                _say("Resuming Step 2 of 4 -- Finding better settings: this stage's own progress isn't saved "
                     "during the quick-test scan (by design, to keep it fast and disposable), so it restarts "
                     "from its first combination -- the backtest above was NOT repeated, only this step.")
            else:
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

            _checkpoint("optimizing", optimizer_done=True,
                        best_candidate=(best_candidate.to_dict() if best_candidate is not None else None),
                        best_desc=best_desc, tried=tried)

        optimized_batch_id = checkpoint.get("optimized_batch_id")
        optimized_summary = checkpoint.get("optimized_summary")
        winner = checkpoint.get("winner", "original")

        if best_candidate is not None and not checkpoint.get("validation_done"):
            optimized_batch_id = optimized_batch_id or runner.new_batch_id()
            _checkpoint("optimizing", optimized_batch_id=optimized_batch_id)
            _stage("optimizing", validating_candidate=best_desc,
                   stage_label="Double-checking the best combination on the full history")
            if checkpoint.get("optimized_batch_id") and is_resuming:
                _say(f"Resuming the full validation of the optimized candidate (batch {optimized_batch_id}) -- "
                     f"coins already completed before the interruption are skipped, not redone.")
            else:
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
                progress_cb=_val_progress_cb, use_multiprocessing=True, batch_id=optimized_batch_id,
                extraction_override_warning=extraction_override_warning,
            )
            if control and control.should_stop():
                return _stopped("optimizing")

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
            _checkpoint("optimizing", optimized_batch_id=optimized_batch_id, optimized_summary=optimized_summary,
                        winner=winner, validation_done=True)
        elif best_candidate is None:
            _say("None of the combinations tried beat the original on the quick test, so the optimized "
                 "version is skipped -- no need to spend time on a full test that won't win anyway. "
                 "Keeping the strategy exactly as imported.")
        else:
            _say(f"The full validation of the optimized candidate (batch {optimized_batch_id}) was already "
                 f"completed before the interruption -- reusing it (winner: {winner}).")

        if control and control.should_stop():
            return _stopped("optimizing")

        # ---------------------------------------------------------- Stage 3/4: comparing
        if not checkpoint.get("comparing_done"):
            _stage("comparing", winner=winner, stage_label="Saving the original vs optimized comparison")
            opt_id = uuid.uuid4().hex[:12]
            params_changed = [{"description": best_desc}] if (winner == "optimized" and best_desc) else []
            storage.save_optimization(
                opt_id, strategy_id, original_batch_id, optimized_batch_id, winner,
                params_changed, tried, _now_iso(),
            )
            _say(f"Step 3 of 4 -- Saving the comparison: you can see the original vs optimized side by side "
                 f"any time in Backtest History (winner: {winner}).")

            # If the optimized candidate won, persist it as a new version of
            # the SAME saved strategy -- strategy_library.load(strategy_id)
            # always returns the current version, so Paper Trading (below)
            # picks up the winning parameters automatically with no
            # export/import step.
            if winner == "optimized" and best_candidate is not None:
                best_candidate.name = cfg.name
                lib.save_version(strategy_id, best_candidate)
                _say(f"Saved the optimized settings as the new version of '{cfg.name}' -- "
                     f"nothing to export or re-import.")
            _checkpoint("starting_paper_trading", comparing_done=True, opt_id=opt_id)
        else:
            _say("Step 3 of 4 -- Saving the comparison: already completed before the interruption.")

        if control and control.should_stop():
            return _stopped("comparing")

        # ---------------------------------------------------------- Stage 3.5: walk-forward testing
        # Checks whether this strategy (or its winning optimized version,
        # if optimizing won above) is genuinely robust, or just tuned to
        # fit whatever already happened in the past -- a SEPARATE,
        # additional check layered on top of the existing Backtest Engine
        # and Auto-Optimizer, not a change to either of them. Informational
        # only: a FAIL here does NOT block Paper Trading below -- this
        # pipeline has no existing precedent for a backtest-quality check
        # halting deployment (the sanity check earlier DOES halt the
        # pipeline, but that catches a strategy that's structurally broken,
        # not one that's merely unconvincing), so the result is saved and
        # surfaced, and the CEO decides what to do with a FAIL from there.
        if not checkpoint.get("walk_forward_done"):
            _stage("walk_forward_testing",
                   stage_label="Checking whether this strategy holds up on data it hasn't seen yet")
            _say("Step 3.5 of 4 -- Walk-Forward Test: splitting this strategy's own historical data "
                 "chronologically (the earliest 70% for training, the most recent 30% for testing -- never "
                 "shuffled, since this checks behavior on genuinely LATER data) to see whether it's actually "
                 "good, or just fit to the past. Re-tuning its settings using ONLY the training period, then "
                 "testing those exact settings on the testing period, which the tuning step never saw.")
            wf_config = best_candidate if (winner == "optimized" and best_candidate is not None) else cfg
            wf_symbol = symbols[0]
            try:
                wf_result = walk_forward.run_walk_forward_test(
                    wf_config, exchange, wf_symbol, dict(settings), log_fn=_say, control=control,
                )
                lib.save_walk_forward_result(strategy_id, wf_result)
                _say(f"Walk-Forward Test verdict: {wf_result['status']} -- {wf_result['reason']}")
            except Exception as exc:
                _say(f"Walk-Forward Test could not complete ({exc!r}) -- this is an informational check, so "
                     f"it doesn't block Paper Trading below; you can re-run it later from the Strategies page.")
            _checkpoint("starting_paper_trading", walk_forward_done=True)
        else:
            _say("Step 3.5 of 4 -- Walk-Forward Test: already completed before the interruption.")

        if control and control.should_stop():
            return _stopped("walk_forward_testing")

        # ---------------------------------------------------------- Stage 4/4: paper trading handoff
        # Idempotent and additive: multiple strategies can run in Paper
        # Trading at the same time, each with its own independent book, so
        # handing off a new strategy never stops or restarts whatever is
        # already running for other strategies -- it only makes sure THIS
        # strategy's config is enabled and that the engine is alive at all.
        _stage("starting_paper_trading", winner=winner, stage_label="Starting Paper Trading with the winning version")
        _say(f"Step 4 of 4 -- Starting Paper Trading: handing the {winner.upper()} version of '{cfg.name}' "
             f"to Paper Trading so SINDHU can start trading it live (simulated) automatically, "
             f"alongside any other strategies already running.")

        from paper_trading.engine import engine as pt_engine
        from sindhu_web.api.paper_trading import _log_and_broadcast, _on_engine_event

        existing_cfg = storage.get_paper_strategy_config(strategy_id)
        if not existing_cfg.get("enabled", True):
            storage.save_paper_strategy_config(
                strategy_id, True, existing_cfg.get("priority", 5),
                existing_cfg.get("supported_coins", []), existing_cfg.get("supported_market_types", []),
                _now_iso(),
            )

        if pt_engine.is_running():
            started = True
            _say(f"Paper Trading is already running -- '{cfg.name}' has been enabled and will join in on the "
                 f"next tick without disturbing any strategy already trading.")
        else:
            started = pt_engine.start(log=_log_and_broadcast, on_event=_on_engine_event)
            if started:
                _say(f"Done -- Paper Trading is now running, starting with '{cfg.name}'.")
            else:
                _say("Could not start Paper Trading (it reported it was still busy shutting down) -- "
                     "you can start it manually from the Paper Trading page.")

        _stage("completed", winner=winner, paper_trading_started=started,
               stage_label="Done -- see the results in Backtest History")
        _checkpoint("completed", paper_trading_attempted=True)
        storage.update_pipeline_job(job_id, _now_iso(), status="completed")
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
    except Exception as exc:
        # Anything genuinely uncaught (a bug, an unexpected data issue) --
        # job_manager's own wrapper already sets job.status="error" in
        # memory, but that's lost on restart; persisting it here too means
        # a crash mid-pipeline is never silently left as status='running'
        # forever, even if the crash happens somewhere this function didn't
        # anticipate.
        storage.update_pipeline_job(job_id, _now_iso(), status="failed", error=repr(exc))
        raise
