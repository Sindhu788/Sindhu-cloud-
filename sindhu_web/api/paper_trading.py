from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backtest_engine import strategy_library as lib
from data_engine import storage
from data_engine.logging_setup import log as file_log
from paper_trading import config as pt_config
from paper_trading.engine import engine
from sindhu_web import broadcast, sync

router = APIRouter()


def _log_and_broadcast(message):
    file_log(message)
    broadcast.publish({"channel": "log", "job_id": "paper_trading", "message": message})


def _on_engine_event(payload):
    broadcast.publish({"channel": "paper", **payload})


@router.get("/api/paper-trading/status")
def get_status():
    return engine.status()


@router.post("/api/paper-trading/start")
def start_engine():
    started = engine.start(log=_log_and_broadcast, on_event=_on_engine_event)
    if not started:
        raise HTTPException(400, "engine already running")
    sync.notify("paper_trading", "started", "Paper Trading engine started")
    return {"ok": True}


@router.post("/api/paper-trading/stop")
def stop_engine():
    stopped = engine.stop()
    if not stopped:
        raise HTTPException(400, "engine already stopped")
    sync.notify("paper_trading", "stopped", "Paper Trading engine stopped")
    return {"ok": True}


@router.post("/api/paper-trading/run-tick-now")
def run_tick_now():
    """Manual single-tick trigger -- used for testing/demoing the pipeline
    without waiting for the next scheduled tick."""
    summary = engine.run_single_tick_now()
    return {"ok": True, "summary": summary}


class SettingsUpdate(BaseModel):
    dry_run: Optional[bool] = None
    initial_balance: Optional[float] = None
    risk_pct_default: Optional[float] = None
    max_open_trades: Optional[int] = None
    cooldown_minutes: Optional[int] = None
    priority_rule: Optional[str] = None
    opposite_signal_policy: Optional[str] = None
    coin_filter_top_n: Optional[int] = None
    tick_interval_seconds: Optional[int] = None
    lookback_days: Optional[int] = None
    lesson_default_timeframe: Optional[str] = None
    lesson_default_sl_pct: Optional[float] = None
    lesson_default_rr: Optional[float] = None
    daily_goal_pct: Optional[float] = None


@router.get("/api/paper-trading/settings")
def get_settings():
    return pt_config.load()


@router.post("/api/paper-trading/settings")
def update_settings(req: SettingsUpdate):
    settings = pt_config.update(**req.dict(exclude_none=True))
    sync.notify("paper_trading", "updated", "Paper Trading settings changed")
    return settings


@router.get("/api/paper-trading/positions")
def get_open_positions(strategy_id: Optional[str] = None):
    return {"positions": storage.get_open_paper_positions(strategy_id=strategy_id)}


@router.get("/api/paper-trading/trades")
def get_closed_trades(limit: int = 100, strategy_id: Optional[str] = None):
    return {"trades": storage.list_closed_paper_positions(limit=limit, strategy_id=strategy_id)}


@router.post("/api/paper-trading/positions/{position_id}/close")
def manual_close(position_id: str):
    from paper_trading import position_manager

    pos = storage.get_paper_position(position_id)
    if not pos:
        raise HTTPException(404, "position not found")
    if pos["status"] != "open":
        raise HTTPException(400, "position already closed")
    closed = position_manager.force_close(position_id, pos["entry_price"], reason="closed_manually")
    sync.notify("paper_trading", "position_closed", f"Position closed manually: {pos['symbol']}")
    return {"ok": True, "trade": closed}


@router.get("/api/paper-trading/decisions")
def get_decisions(decision: Optional[str] = None, limit: int = 100):
    return {"decisions": storage.list_paper_decisions(decision=decision, limit=limit)}


@router.get("/api/paper-trading/strategy-performance")
def get_strategy_performance():
    return {"performance": storage.list_paper_strategy_performance()}


@router.get("/api/paper-trading/lesson-performance")
def get_lesson_performance():
    return {"performance": storage.list_paper_lesson_performance()}


@router.get("/api/paper-trading/strategy-config/{strategy_id}")
def get_strategy_config(strategy_id: str):
    return storage.get_paper_strategy_config(strategy_id)


class StrategyConfigUpdate(BaseModel):
    enabled: bool = True
    priority: int = 5
    supported_coins: list = []
    supported_market_types: list = []


@router.post("/api/paper-trading/strategy-config/{strategy_id}")
def update_strategy_config(strategy_id: str, req: StrategyConfigUpdate):
    storage.save_paper_strategy_config(
        strategy_id, req.enabled, req.priority, req.supported_coins,
        req.supported_market_types, datetime.now(timezone.utc).isoformat(),
    )
    sync.notify("paper_trading", "updated", "Paper strategy config updated", id=strategy_id)
    return {"ok": True}


def _period_bounds(period):
    """UTC-based, matching how every timestamp in paper_positions is
    stored (datetime.now(timezone.utc).isoformat()). Returns
    (since_iso, until_iso); either side may be None (unbounded)."""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "today":
        return today_start.isoformat(), None
    if period == "yesterday":
        y_start = today_start - timedelta(days=1)
        return y_start.isoformat(), today_start.isoformat()
    if period == "week":
        week_start = today_start - timedelta(days=today_start.weekday())
        return week_start.isoformat(), None
    if period == "month":
        month_start = today_start.replace(day=1)
        return month_start.isoformat(), None
    return None, None  # "all"


@router.get("/api/paper-trading/analytics")
def get_analytics(period: str = "all"):
    """The single data source behind both the Paper Trading page's
    analytics dashboard and the SINDHU CEO Paper Trading card's expanded
    view (CEO-parity rule) -- closed trades only count once actually
    closed; open positions are always reported as a separate count, never
    folded into closed_trades."""
    since_iso, until_iso = _period_bounds(period)
    summary = storage.get_paper_period_summary(since_iso, until_iso)
    coin_stats = storage.list_paper_coin_stats(since_iso, until_iso)
    strategy_stats = storage.list_paper_strategy_stats(since_iso, until_iso)

    # A strategy currently enabled but with zero closed trades (brand new,
    # or only open positions so far) still needs to show up, not just ones
    # with history -- and a strategy since disabled or deleted from the
    # library keeps its permanent record either way (it just won't get a
    # live name refresh below).
    configs = storage.list_paper_strategy_configs()
    trading_since = storage.list_paper_strategy_trading_since()
    metas = lib.list_all()
    live_names = {m["id"]: m["name"] for m in metas}
    known = {s["strategy_id"] for s in strategy_stats}
    for meta in metas:
        sid = meta["id"]
        if sid in known or not configs.get(sid, {}).get("enabled"):
            continue
        strategy_stats.append({
            "strategy_id": sid, "strategy_name": meta["name"], "closed_trades": 0,
            "total_pnl": 0.0, "win_count": 0, "win_rate": 0.0,
            "trading_since": trading_since.get(sid),
        })
    for s in strategy_stats:
        if s["strategy_id"] in live_names:
            s["strategy_name"] = live_names[s["strategy_id"]]  # prefer the current name over a stale one
    strategy_stats.sort(key=lambda s: s["total_pnl"], reverse=True)

    open_positions = storage.get_open_paper_positions()
    open_by_strategy = {}
    for p in open_positions:
        key = p.get("strategy_id") or "__lessons__"
        open_by_strategy[key] = open_by_strategy.get(key, 0) + 1
    for s in strategy_stats:
        s["open_positions"] = open_by_strategy.get(s["strategy_id"], 0)

    return {
        "period": period,
        "summary": summary,
        "open_positions_count": len(open_positions),
        "best_coin": coin_stats[0] if coin_stats else None,
        "worst_coin": coin_stats[-1] if coin_stats else None,
        "per_coin": coin_stats,
        "per_strategy": strategy_stats,
    }
