import uuid
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from data_engine import storage
from data_engine.control import DownloadControl
from backtest_engine.strategy_parser import parse_strategy_text
from backtest_engine.strategy_config import StrategyConfig
from backtest_engine.validator import validate
from backtest_engine import strategy_library as lib
from backtest_engine import runner
from backtest_engine.reports import generate_report
from sindhu_web.jobs import job_manager
from sindhu_web.api.data import _default_exchange
from sindhu_web import sync

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
            sync.notify("strategy", "updated", f"Strategy updated: {cfg.name}", id=strategy_id)
            return {"id": strategy_id}
        except FileNotFoundError:
            pass
    strategy_id = lib.create(cfg, tags=req.tags)
    sync.notify("strategy", "created", f"Strategy added: {cfg.name}", id=strategy_id)
    return {"id": strategy_id}


def _strategy_last_batch_result(strategy_name):
    """Lightweight summary straight from each result's already-computed
    metrics_json -- deliberately NOT generate_report(), which also builds
    full rankings/session analysis and writes report.json/.txt to disk on
    every call. That's the right tool for viewing one report, but calling
    it once per strategy just to populate a list view made this endpoint
    scale badly (measured ~800ms per strategy) and made the Strategies/
    Backtesting pages feel like they'd hung on load."""
    for batch in storage.list_recent_batches(limit=100):
        if batch["strategy_name"] != strategy_name:
            continue
        if batch["status"] != "completed":
            return {"batch_id": batch["batch_id"], "status": batch["status"], "created_at": batch["created_at"]}
        results = storage.get_batch_results(batch["batch_id"])
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


@router.get("/api/backtesting/strategies")
def list_strategies(q: str = ""):
    strategies = lib.search(q)
    for meta in strategies:
        try:
            cfg = lib.load(meta["id"])
            meta["concepts_used"] = cfg.concepts_used
            meta["timeframes"] = cfg.timeframes
            meta["status"] = "READY_FOR_BACKTEST" if not validate(cfg) else "NEEDS_CLARIFICATION"
        except Exception:
            meta["concepts_used"], meta["timeframes"], meta["status"] = [], {}, "NEEDS_CLARIFICATION"
        meta["last_batch_result"] = _strategy_last_batch_result(meta["name"])
    return {"strategies": strategies}


@router.get("/api/backtesting/strategies/{strategy_id}/versions")
def get_strategy_versions(strategy_id: str):
    return {"versions": lib.version_history(strategy_id)}


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
    return {"config": cfg.to_dict(), "errors": errors, "valid": not errors}


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

    def _trade_cb(symbol, timeframe, trade):
        job_manager.update_progress(job_id, last_trade={
            "symbol": symbol, "timeframe": timeframe, "side": trade["side"],
            "pnl": trade["pnl"], "trade_num": trade["trade_num"],
            "entry_reason": trade.get("entry_reason"), "exit_reason": trade.get("exit_reason"),
        })

    log_fn = job_manager.make_log_fn(job_id)

    def _target():
        batch_id = runner.run_mtf_batch(
            cfg, exchange, symbols, settings,
            start_ms=settings["start_ms"], end_ms=settings["end_ms"],
            log=log_fn, control=control, progress_cb=_progress_cb, trade_cb=_trade_cb,
            use_multiprocessing=req.use_multiprocessing,
        )
        generate_report(batch_id)
        return {"batch_id": batch_id}

    job_manager.create_job("backtest", _target, control=control, job_id=job_id)
    sync.notify("backtest", "started", f"Backtesting started: {cfg.name}", job_id=job_id)
    return {"job_id": job_id}
