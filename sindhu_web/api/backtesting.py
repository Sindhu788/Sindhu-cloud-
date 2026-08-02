import hashlib
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from data_engine import storage
from data_engine.control import DownloadControl
from backtest_engine.strategy_parser import parse_strategy_text
from backtest_engine.strategy_config import StrategyConfig
from backtest_engine.validator import validate
from backtest_engine.strategy_safety_check import run_safety_check
from backtest_engine.performance_dashboard import evaluate_strategy_performance
from backtest_engine import strategy_library as lib
from backtest_engine import runner
from backtest_engine import sanity_check
from backtest_engine.reports import generate_report
from backtest_engine import monte_carlo, stress_test
from automation_pipeline import optimizer as grid_optimizer
from automation_pipeline import genetic_optimizer
from ai_integration import extraction_lock, multi_pass_extraction
from data_engine.resample import get_ohlcv
from sindhu_web.jobs import job_manager
from sindhu_web.api.data import _default_exchange
from sindhu_web import sync, cache


def _now_iso():
    return datetime.now(timezone.utc).isoformat()

router = APIRouter()


class ParseRequest(BaseModel):
    text: str
    name: str = "Unnamed Strategy"


@router.post("/api/backtesting/parse")
def parse_strategy(req: ParseRequest):
    cfg = parse_strategy_text(req.text, name=req.name)
    errors = validate(cfg)
    return {"config": cfg.to_dict(), "errors": errors, "valid": not errors}


class SaveRequest(BaseModel):
    config: Dict[str, Any]
    tags: List[str] = []
    strategy_id: Optional[str] = None


@router.post("/api/backtesting/strategies")
def save_strategy(req: SaveRequest):
    """If strategy_id is given, updates that existing strategy (new
    version) instead of creating a new one -- this is what lets the
    frontend autosave on every edit without piling up duplicate records.
    If no strategy_id is given but a strategy with the SAME NAME already
    exists, that one is updated (a new version) too -- saving a strategy
    under a name that's already in the library must never silently create
    a second, duplicate entry."""
    cfg = StrategyConfig.from_dict(req.config)
    strategy_id = req.strategy_id or lib.find_by_name(cfg.name)
    if strategy_id:
        try:
            lib.save_version(strategy_id, cfg)
            cache.invalidate(_STRATEGIES_CACHE_KEY)
            sync.notify("strategy", "updated", f"Strategy updated: {cfg.name}", id=strategy_id)
            return {"id": strategy_id}
        except FileNotFoundError:
            pass
    strategy_id = lib.create(cfg, tags=req.tags)
    cache.invalidate(_STRATEGIES_CACHE_KEY)
    sync.notify("strategy", "created", f"Strategy added: {cfg.name}", id=strategy_id)
    return {"id": strategy_id}


def _strategy_last_batch_result(strategy_name, recent_batches, batch_results_cache=None):
    """Lightweight summary straight from each result's already-computed
    metrics_json -- deliberately NOT generate_report(), which also builds
    full rankings/session analysis and writes report.json/.txt to disk on
    every call. That's the right tool for viewing one report, but calling
    it once per strategy just to populate a list view made this endpoint
    scale badly (measured ~800ms per strategy) and made the Strategies/
    Backtesting pages feel like they'd hung on load.

    `recent_batches` is fetched once by the caller and reused across every
    strategy in the list -- list_strategies() used to call
    storage.list_recent_batches(limit=100) freshly inside this function for
    EVERY strategy (a DB round trip + JSON-parsing up to 100 batches, N
    times over for N strategies), which is exactly the kind of redundant
    per-item query this endpoint is also polled by the Paper Trading page
    load (it lists available strategies), so it compounds with everything
    else fetched on that page."""
    for batch in recent_batches:
        if batch["strategy_name"] != strategy_name:
            continue
        if batch["status"] != "completed":
            return {"batch_id": batch["batch_id"], "status": batch["status"], "created_at": batch["created_at"]}
        if batch_results_cache is not None and batch["batch_id"] in batch_results_cache:
            results = batch_results_cache[batch["batch_id"]]
        else:
            results = storage.get_batch_results(batch["batch_id"])
            if batch_results_cache is not None:
                batch_results_cache[batch["batch_id"]] = results
        completed = [r for r in results if r["status"] == "completed" and r["metrics"]]
        if not completed:
            return {"batch_id": batch["batch_id"], "status": "completed", "created_at": batch["created_at"], "total_trades": 0}
        total_trades = sum(r["metrics"]["total_trades"] for r in completed)
        wins = sum(r["metrics"]["wins"] for r in completed)
        return {
            "batch_id": batch["batch_id"], "status": "completed", "created_at": batch["created_at"],
            "total_trades": total_trades, "symbols_tested": len(completed),
            "win_rate": round((wins / total_trades * 100) if total_trades else 0.0, 2),
            "avg_profit_pct": round(sum(r["metrics"]["profit_pct"] for r in completed) / len(completed), 2),
        }
    return None


def _condition_roles_summary(cfg):
    """[{bucket, type, name, direction, role}] for every concept condition
    -- lets the Strategies page show which declared timeframe (bias/trend/
    analysis/entry) each condition actually reads from, instead of that
    being invisible plumbing. role is always a real value here (never
    null) -- unset means the entry-timeframe default, shown explicitly so
    the CEO isn't left guessing whether it was never checked or is
    deliberately on entry."""
    out = []
    for bucket in ("entry_conditions", "long_entry_conditions", "short_entry_conditions",
                   "exit_conditions", "confirmation_conditions"):
        for cond in getattr(cfg, bucket, []):
            if cond.type == "concept":
                out.append({
                    "bucket": bucket, "name": cond.name, "direction": cond.direction,
                    "role": cond.role or "entry",
                })
            elif cond.type == "indicator_vs_indicator":
                p1 = (cond.params or {}).get("period")
                p2 = (cond.params2 or {}).get("period")
                out.append({
                    "bucket": bucket, "name": f"{cond.indicator}{p1 or ''} {cond.op} {cond.indicator2}{p2 or ''}",
                    "direction": None, "role": cond.role or "entry",
                })
    return out


def _compute_strategies_list(q):
    strategies = lib.search(q)
    recent_batches = storage.list_recent_batches(limit=100)
    # Batch 3, Task 3: one bulk query for every strategy's lock status
    # instead of one round-trip per strategy in the loop below -- this
    # list is polled/loaded frequently, and N separate small queries
    # measured 130+ seconds under real DB load (other writers holding the
    # SQLite file busy) versus a single query.
    lock_statuses = extraction_lock.check_strategy_locks_bulk([m["id"] for m in strategies])
    # Batch 4, Task 1: _strategy_last_batch_result and evaluate_strategy_
    # performance each independently fetch storage.get_batch_results() for
    # the SAME batch_id when a strategy has one -- this shared dict lets the
    # second call reuse the first's result instead of opening a second DB
    # connection, halving that part of the endpoint's real DB round trips.
    batch_results_cache = {}
    for meta in strategies:
        try:
            cfg = lib.load(meta["id"])
            meta["concepts_used"] = cfg.concepts_used
            meta["timeframes"] = cfg.timeframes
            validator_errors = validate(cfg)
            safety = run_safety_check(cfg)
            # Automatic Strategy Safety Check (computed live, not from the
            # cached meta.json value, so the list is never stale even for a
            # strategy saved before this check existed and not yet
            # backfilled): validator errors (missing/invalid fields) take
            # priority since those block backtesting outright; a strategy
            # that's structurally valid but fails the safety check is
            # "Needs Review", not silently shown as ready.
            if validator_errors:
                meta["status"] = "NEEDS_CLARIFICATION"
            elif not safety["passed"]:
                meta["status"] = "NEEDS_REVIEW"
            else:
                meta["status"] = "READY_FOR_BACKTEST"
            meta["safety_reasons"] = safety["reasons"]
            meta["condition_roles"] = _condition_roles_summary(cfg)
        except Exception:
            meta["concepts_used"], meta["timeframes"], meta["status"] = [], {}, "NEEDS_CLARIFICATION"
            meta["safety_reasons"] = []
            meta["condition_roles"] = []
        meta["last_batch_result"] = _strategy_last_batch_result(
            meta["name"], recent_batches, batch_results_cache=batch_results_cache)
        lock_status = lock_statuses.get(meta["id"], {"locked": False, "overridden": False})
        meta["extraction_locked"] = lock_status["locked"]
        meta["extraction_overridden"] = lock_status["overridden"]
        # Strategy Performance Dashboard (display-only -- reads already-
        # computed backtest/walk-forward results, never runs anything, never
        # blocks or removes a strategy): a single GREEN/RED verdict combining
        # expectancy, profit factor, trade count, and Walk-Forward status.
        try:
            performance = evaluate_strategy_performance(
                meta["id"], recent_batches=recent_batches, batch_results_cache=batch_results_cache)
        except Exception:
            performance = None
        meta["performance_verdict"] = performance["verdict"] if performance else None
        meta["performance_label"] = performance["label"] if performance else None
        meta["performance_failed_factors"] = performance["failed_factors"] if performance else []
    return strategies


# Batch 4, Task 1: this endpoint is polled by both the Strategies and Paper
# Trading pages and was measured taking 30-60+ seconds under real DB write
# contention -- see get_conn()'s synchronous=NORMAL fix for the underlying
# cause. A short stale-while-revalidate cache (sindhu_web.cache, the same
# pattern /api/home already uses) means only the very first cold call per
# TTL window pays that cost; every poll within the window gets the last
# computed snapshot instantly. Only the no-search-term case (q="") is
# cached -- that's the one actually hammered by repeated page polls: the
# search box is a deliberate one-off user action where a stale result would
# be actively misleading, so q != "" always computes fresh. save_strategy()
# below explicitly invalidates this key so a newly created/edited strategy
# is never hidden behind a stale cache entry.
_STRATEGIES_CACHE_KEY = "strategies_list:all"
_STRATEGIES_CACHE_TTL = 10


@router.get("/api/backtesting/strategies")
def list_strategies(q: str = ""):
    if q:
        return {"strategies": _compute_strategies_list(q)}
    return {"strategies": cache.cached(
        _STRATEGIES_CACHE_KEY, _STRATEGIES_CACHE_TTL, lambda: _compute_strategies_list(""))}


@router.get("/api/backtesting/strategies/{strategy_id}/versions")
def get_strategy_versions(strategy_id: str):
    return {"versions": lib.version_history(strategy_id)}


# --------------------------------------------------------------- Batch 3, Task 3: Verification View + Incomplete Lock

class ExtractionOverrideRequest(BaseModel):
    overridden: bool


@router.get("/api/backtesting/strategies/{strategy_id}/extraction-verification")
def get_extraction_verification(strategy_id: str):
    """Side-by-side view data (Task 3): each row is the user's own
    document text next to a plain Roman Urdu/Hinglish description of what
    was understood, plus a captured/missing mark and an overall
    plain-language summary. Also whether this strategy is currently
    locked out of backtesting/optimization/paper trading."""
    try:
        lib.load(strategy_id)
    except FileNotFoundError:
        raise HTTPException(404, "strategy not found")
    return extraction_lock.verification_summary(strategy_id)


@router.post("/api/backtesting/strategies/{strategy_id}/extraction-override")
def set_extraction_override(strategy_id: str, req: ExtractionOverrideRequest):
    """The explicit "test anyway" override -- persistent, so every
    backtest/optimize/paper-trading run for this strategy from now on
    (until un-overridden) is permitted but permanently tagged with a
    visible warning (extraction_override_warning on the resulting
    batches)."""
    try:
        lib.load(strategy_id)
    except FileNotFoundError:
        raise HTTPException(404, "strategy not found")
    report = storage.get_extraction_fidelity_report_for_strategy(strategy_id)
    if report is None:
        raise HTTPException(400, "Is strategy ka koi verification report nahi hai -- override karne ki zaroorat nahi.")
    extraction_lock.set_override(strategy_id, req.overridden)
    sync.notify("strategy", "extraction_override_changed",
                f"{'Override ON' if req.overridden else 'Override OFF'} for {strategy_id}", id=strategy_id)
    return extraction_lock.verification_summary(strategy_id)


@router.post("/api/backtesting/strategies/{strategy_id}/extraction-audit")
def run_extraction_audit(strategy_id: str):
    """Retroactive audit (Task 3, requirement 5): runs the SAME multi-pass
    + auto-retry pipeline (Tasks 1/2) against an already-saved strategy's
    original document text, for strategies imported before this feature
    existed (no report yet) or a CEO-requested re-check. Real AI calls --
    not instant, and subject to the same provider fallback chain/quota as
    any other extraction."""
    try:
        cfg = lib.load(strategy_id)
    except FileNotFoundError:
        raise HTTPException(404, "strategy not found")
    if not cfg.raw_text or not cfg.raw_text.strip():
        raise HTTPException(400, "Is strategy ka original document text save nahi hai -- audit nahi ho sakta.")

    content_hash = hashlib.sha256(cfg.raw_text.strip().lower().encode("utf-8")).hexdigest()
    mp = multi_pass_extraction.run_multi_pass_extraction_with_retry(cfg.raw_text, content_type="strategy")
    now_iso = _now_iso()
    storage.save_extraction_fidelity_report(
        content_hash, mp["comparison"]["expected_count"], mp["comparison"]["captured_count"],
        mp["call_count"], mp["comparison"]["rules"], mp["provider"], now_iso, retry_count=mp["retry_count"],
    )
    storage.set_extraction_fidelity_strategy_id(content_hash, strategy_id)
    sync.notify("strategy", "extraction_audited",
                f"Verification check done for {cfg.name}: {mp['comparison']['captured_count']}/{mp['comparison']['expected_count']} rules understood",
                id=strategy_id)
    return extraction_lock.verification_summary(strategy_id)


@router.get("/api/backtesting/strategies/{strategy_id}")
def get_strategy(strategy_id: str):
    try:
        cfg = lib.load(strategy_id)
    except FileNotFoundError:
        raise HTTPException(404, "strategy not found")
    # Includes the same validity check the strategy list uses -- the
    # Backtesting page needs this to show an accurate preview right after
    # Load without re-parsing raw_text (see frontend comment for why that's
    # unsafe for AI-imported strategies).
    errors = validate(cfg)
    safety = run_safety_check(cfg)
    performance = evaluate_strategy_performance(strategy_id)
    return {
        "config": cfg.to_dict(), "errors": errors, "valid": not errors,
        "safety_status": safety["status"], "safety_reasons": safety["reasons"],
        "performance": performance,
    }


@router.delete("/api/backtesting/strategies/{strategy_id}")
def delete_strategy(strategy_id: str):
    lib.delete(strategy_id)
    sync.notify("strategy", "deleted", "Strategy deleted", id=strategy_id)
    return {"ok": True}


@router.post("/api/backtesting/strategies/{strategy_id}/favourite")
def favourite_strategy(strategy_id: str, favourite: bool = True):
    lib.set_favourite(strategy_id, favourite)
    sync.notify("strategy", "updated", "Strategy favourite toggled", id=strategy_id)
    return {"ok": True}


@router.post("/api/backtesting/strategies/{strategy_id}/duplicate")
def duplicate_strategy(strategy_id: str):
    new_id = lib.duplicate(strategy_id)
    sync.notify("strategy", "created", "Strategy duplicated", id=new_id)
    return {"id": new_id}


@router.get("/api/backtesting/coins")
def list_coins():
    exchange = _default_exchange()
    return {"exchange": exchange, "symbols": storage.load_symbols(exchange)}


# --------------------------------------------------------------- Monte Carlo Engine (Group 6 #4)

@router.get("/api/backtesting/monte-carlo/{batch_id}")
def get_monte_carlo(batch_id: str, iterations: int = 1000):
    return monte_carlo.run_monte_carlo(batch_id, iterations=iterations)


# --------------------------------------------------------------- Stress Testing Engine (B5)

@router.get("/api/backtesting/stress-test/{strategy_id}/{symbol}")
def get_stress_test(strategy_id: str, symbol: str):
    exchange = _default_exchange()
    return stress_test.run_stress_test(strategy_id, exchange, symbol)


# --------------------------------------------------------------- Genetic Optimization Engine (B6)

@router.get("/api/backtesting/genetic-optimize/{strategy_id}/{symbol}")
def get_genetic_optimize(strategy_id: str, symbol: str, days: int = 30,
                          population_size: int = 10, generations: int = 5):
    """Runs BOTH the existing grid-search optimizer and the new genetic
    optimizer on the exact same strategy/symbol/date-window, so the two
    can be directly compared. Neither writes anything to the database --
    same in-memory-only contract _run_in_memory already guarantees."""
    exchange = _default_exchange()
    min_ms, max_ms = storage.get_symbol_time_bounds(exchange, symbol)
    if min_ms is None:
        return {"available": False, "reason": f"no stored data for {symbol}"}
    start_ms = max(min_ms, max_ms - days * 86400 * 1000)
    end_ms = max_ms

    try:
        cfg = lib.load(strategy_id)
    except Exception as e:
        return {"available": False, "reason": f"could not load strategy: {e!r}"}

    settings = {"initial_balance": 10000.0}

    best_cfg, tried_log, best_description = grid_optimizer.optimize(cfg, exchange, symbol, settings, start_ms, end_ms)
    grid_metrics = None
    if best_cfg is not None:
        grid_metrics = grid_optimizer._run_in_memory(best_cfg, exchange, symbol, settings, start_ms, end_ms)
    grid_result = {
        "candidates_tried": len(tried_log), "best_description": best_description,
        "best_metrics": grid_metrics,
    }

    genetic_result = genetic_optimizer.run_genetic_optimization(
        cfg, exchange, symbol, settings, start_ms, end_ms,
        population_size=population_size, generations=generations,
    )

    return {"available": True, "strategy_id": strategy_id, "symbol": symbol,
            "window_days": days, "grid_search": grid_result, "genetic": genetic_result}


# --------------------------------------------------------------- Trade Audit Engine (Group 6 #5)

@router.get("/api/backtesting/trade-audit/{batch_id}/{symbol}/{timeframe}/{trade_num}")
def get_trade_audit(batch_id: str, symbol: str, timeframe: str, trade_num: int):
    """Full manual-verification detail for one backtest trade: the exact
    entry/exit rule that fired (already recorded at trade time, not
    re-derived), and the raw 1-minute candles spanning the trade so the
    entry/exit prices can be checked against real market data by hand."""
    trades = storage.get_trades(batch_id, symbol=symbol, timeframe=timeframe)
    trade = next((t for t in trades if t["trade_num"] == trade_num), None)
    if not trade:
        raise HTTPException(404, "trade not found")

    exchange = _default_exchange()
    start_ms = trade["entry_time"] - 30 * 60 * 1000  # 30min padding before entry
    end_ms = (trade["exit_time"] or trade["entry_time"]) + 30 * 60 * 1000
    try:
        df = get_ohlcv(exchange, symbol, interval="1m", start_ms=start_ms, end_ms=end_ms)
        candles = [
            {"time": int(idx.timestamp() * 1000), "open": row.open, "high": row.high,
             "low": row.low, "close": row.close, "volume": row.volume}
            for idx, row in df.iterrows()
        ]
    except Exception:
        candles = []

    return {"trade": trade, "candles": candles}


class RunRequest(BaseModel):
    strategy_id: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    symbols: Optional[List[str]] = None
    all_coins: bool = True
    initial_balance: float = 1000.0
    risk_pct: Optional[float] = None
    commission_pct: float = 0.1
    slippage_pct: float = 0.05
    position_size_pct: float = 10.0
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    use_multiprocessing: bool = True


@router.post("/api/backtesting/run")
def run_backtest(req: RunRequest):
    running = job_manager.get_running_job_of_kind("backtest")
    if running is not None:
        p = running.progress or {}
        done = p.get("done")
        total = p.get("total")
        strategy_name = p.get("current_strategy") or "a strategy"
        progress_desc = f"{done}/{total} coins" if done is not None and total is not None else "in progress"
        raise HTTPException(
            409,
            f"A backtest is already running ({strategy_name}, {progress_desc}). "
            f"Please wait for it to finish or stop it first (job {running.id}).",
        )

    if req.strategy_id:
        cfg = lib.load(req.strategy_id)
    elif req.config:
        cfg = StrategyConfig.from_dict(req.config)
    else:
        raise HTTPException(400, "strategy_id or config required")

    # Batch 3, Task 3: Incomplete Lock -- a strategy with rules the
    # system still couldn't understand (after Task 2's retries) is
    # blocked here, before any real backtest work starts, unless the CEO
    # already explicitly overrode it (see /api/strategies/{id}/
    # extraction-override). Plain Roman Urdu/Hinglish message, no jargon.
    extraction_override_warning = False
    if req.strategy_id:
        lock_status = extraction_lock.check_strategy_lock(req.strategy_id)
        if lock_status["locked"]:
            raise HTTPException(423, extraction_lock.lock_message(lock_status))
        extraction_override_warning = lock_status["overridden"] and bool(lock_status["missing_rules"])

    errors = validate(cfg)
    if errors:
        raise HTTPException(400, {"errors": errors})

    exchange = _default_exchange()
    symbols = req.symbols if (req.symbols and not req.all_coins) else storage.load_symbols(exchange)
    if not symbols:
        raise HTTPException(400, "no coins available for this exchange")

    settings = {
        "initial_balance": req.initial_balance,
        "risk_pct": req.risk_pct or cfg.risk_pct or 1.0,
        "commission_pct": req.commission_pct,
        "slippage_pct": req.slippage_pct,
        "position_size_pct": req.position_size_pct,
        "start_ms": req.start_ms, "end_ms": req.end_ms,
    }

    # Part 3: a fast 1-2 coin / short-date-range check BEFORE committing to
    # the full (potentially 50-coin) run below -- catches a structural
    # 0-trade strategy (a condition that never fires even once) right away
    # instead of after the whole backtest finishes.
    sanity = sanity_check.run_sanity_check(cfg.to_dict(), exchange, symbols, settings)
    if not sanity["ok"]:
        raise HTTPException(400, {
            "errors": [sanity["reason"]],
            "diagnosis": sanity["diagnosis"],
            "sanity_check_failed": True,
        })

    control = DownloadControl()
    job_id = uuid.uuid4().hex[:12]

    def _progress_cb(done, total, symbol, timeframe, stage=None, bar_pct=None,
                      trades_so_far=None, eta_seconds=None):
        job_manager.update_progress(
            job_id, done=done, total=total, current_coin=symbol,
            current_timeframe=timeframe, current_strategy=cfg.name,
            current_stage=stage, bar_pct=bar_pct,
            trades_so_far=trades_so_far, eta_seconds=eta_seconds,
        )

    # Running trade stats (total/wins/cumulative pnl/peak/drawdown/equity
    # curve) used to be tracked ONLY in the browser tab's own JS variables,
    # rebuilt one WebSocket "last_trade" event at a time -- fine while the
    # tab stays open, but navigating away and back created a fresh
    # renderBacktesting() call with those variables reset to zero, even
    # though the backtest was still running fine server-side. job.progress
    # already persisted done/total/current_coin/etc, but never the trade
    # aggregates, so those specific fields looked "reset" on return. Kept
    # here (not in job_manager) since it's request-scoped, one dict per
    # running batch, mirroring _progress_cb's own closure just above.
    trade_stats = {"total_trades": 0, "wins": 0, "cumulative_pnl": 0.0, "peak_pnl": 0.0,
                   "max_drawdown": 0.0, "equity_curve": []}

    def _trade_cb(symbol, timeframe, trade):
        trade_stats["total_trades"] += 1
        if trade["pnl"] > 0:
            trade_stats["wins"] += 1
        trade_stats["cumulative_pnl"] += trade["pnl"]
        trade_stats["peak_pnl"] = max(trade_stats["peak_pnl"], trade_stats["cumulative_pnl"])
        trade_stats["max_drawdown"] = max(trade_stats["max_drawdown"],
                                           trade_stats["peak_pnl"] - trade_stats["cumulative_pnl"])
        trade_stats["equity_curve"].append(round(trade_stats["cumulative_pnl"], 4))
        if len(trade_stats["equity_curve"]) > 500:  # cap -- this is a live progress sparkline,
            trade_stats["equity_curve"] = trade_stats["equity_curve"][-500:]  # not the final report

        job_manager.update_progress(
            job_id,
            last_trade={
                "symbol": symbol, "timeframe": timeframe, "side": trade["side"],
                "pnl": trade["pnl"], "trade_num": trade["trade_num"],
                "entry_reason": trade.get("entry_reason"), "exit_reason": trade.get("exit_reason"),
            },
            total_trades=trade_stats["total_trades"], wins=trade_stats["wins"],
            cumulative_pnl=round(trade_stats["cumulative_pnl"], 4),
            max_drawdown=round(trade_stats["max_drawdown"], 4),
            equity_curve=trade_stats["equity_curve"],
        )

    log_fn = job_manager.make_log_fn(job_id)

    def _target():
        batch_id = runner.run_mtf_batch(
            cfg, exchange, symbols, settings,
            start_ms=settings["start_ms"], end_ms=settings["end_ms"],
            log=log_fn, control=control, progress_cb=_progress_cb, trade_cb=_trade_cb,
            use_multiprocessing=req.use_multiprocessing,
            extraction_override_warning=extraction_override_warning,
        )
        generate_report(batch_id)
        return {"batch_id": batch_id}

    job_manager.create_job("backtest", _target, control=control, job_id=job_id)
    sync.notify("backtest", "started", f"Backtesting started: {cfg.name}", job_id=job_id)
    return {"job_id": job_id}
