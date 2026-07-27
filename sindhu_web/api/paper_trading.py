from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backtest_engine import strategy_library as lib
from backtest_engine import validator
from backtest_engine.strategy_safety_check import run_safety_check
from data_engine import storage
from data_engine.logging_setup import log as file_log
from paper_trading import config as pt_config, insights
from paper_trading import drawdown_guard, regime
from paper_trading.engine import engine
from data_engine import config as base_config
from sindhu_web import broadcast, cache, sync

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
    trades = storage.list_closed_paper_positions(limit=limit, strategy_id=strategy_id)
    for t in trades:
        t["win_loss_tag"] = insights.classify_win_loss(t)
        t["reason_plain"] = insights.humanize_reason(t.get("entry_reason"))
    return {"trades": trades}


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


def _compute_analytics(period):
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
    overrides = storage.list_paper_strategy_overrides()
    account_states = {s["strategy_id"]: s for s in storage.list_paper_account_states()}
    initial_balance = pt_config.load().get("initial_balance", 10000.0)
    # Each of these does ONE query across all strategies rather than one
    # query per strategy -- with 14 active strategies, a naive per-strategy
    # loop here made /api/paper-trading/analytics itself slow enough to
    # time out, the exact class of bug just fixed elsewhere today.
    confidence_scores = insights.all_confidence_scores()
    streaks = insights.all_streaks()
    for s in strategy_stats:
        sid = s["strategy_id"]
        s["open_positions"] = open_by_strategy.get(sid, 0)
        s["confidence_score"] = confidence_scores.get(sid)  # Group 2 #2
        s["streak"] = streaks.get(sid, {"type": "none", "count": 0})  # Group 3 #14
        s["manual_alert"] = overrides.get(sid, {}).get("manual_alert", False)  # Group 1
        acct = account_states.get(sid)
        s["balance"] = round(initial_balance + acct["realized_pnl_total"], 2) if acct else initial_balance  # Group 2 #4

    new_alerts = insights.detect_alerts(strategy_stats, streaks=streaks)  # Group 2 #8/#9

    return {
        "new_alerts": new_alerts,
        "period": period,
        "summary": summary,
        "open_positions_count": len(open_positions),
        "best_coin": coin_stats[0] if coin_stats else None,
        "worst_coin": coin_stats[-1] if coin_stats else None,
        "per_coin": coin_stats,
        "per_strategy": strategy_stats,
    }


@router.get("/api/paper-trading/analytics")
def get_analytics(period: str = "all"):
    """The single data source behind both the Paper Trading page's
    analytics dashboard and the SINDHU CEO Paper Trading card's expanded
    view (CEO-parity rule) -- closed trades only count once actually
    closed; open positions are always reported as a separate count, never
    folded into closed_trades.

    Cached for a short 10s TTL (same stale-while-revalidate pattern as
    /api/home) -- this endpoint runs 6+ separate aggregation queries plus a
    strategy_library disk read with no caching at all, and is polled by
    both the Paper Trading page's own auto-refresh AND the SINDHU CEO
    card whenever it's open, from however many browser tabs/devices are
    connected on the LAN at once. Under concurrent access those requests
    now queue behind data_engine.storage's process-wide write-serialization
    lock (see storage.get_conn()) one full aggregation pass at a time;
    caching means most polls hit the 10s-old value instead of triggering
    (and queuing behind) a fresh pass every single time."""
    return cache.cached(f"paper_analytics_{period}", 10, lambda: _compute_analytics(period))


# --------------------------------------------------------------- Group 1: Manual Override

class OverrideUpdate(BaseModel):
    manual_alert: bool
    note: Optional[str] = None


@router.post("/api/paper-trading/override/{strategy_id}")
def set_strategy_override(strategy_id: str, req: OverrideUpdate):
    """Manual Override: flag this strategy for a Telegram alert regardless
    of its automatic score. No Telegram bot is connected in this build yet
    -- this records the flag (visible in the UI and the activity log) so
    it's ready to wire up to real delivery without lying about having
    already sent anything."""
    now = datetime.now(timezone.utc).isoformat()
    storage.save_paper_strategy_override(strategy_id, req.manual_alert, req.note, now)
    if req.manual_alert:
        _log_and_broadcast(f"[paper-trading] MANUAL OVERRIDE: {strategy_id} flagged for Telegram alert"
                            + (f" -- {req.note}" if req.note else ""))
    sync.notify("paper_trading", "updated", "Manual override updated", id=strategy_id)
    return {"ok": True, "override": storage.get_paper_strategy_override(strategy_id)}


@router.get("/api/paper-trading/overrides")
def get_strategy_overrides():
    return {"overrides": storage.list_paper_strategy_overrides()}


# --------------------------------------------------------------- Group 2: session/coin splits, alerts

@router.get("/api/paper-trading/session-stats")
def get_session_stats(strategy_id: Optional[str] = None, period: str = "all"):
    since_iso, until_iso = _period_bounds(period)
    return {"sessions": storage.list_paper_session_stats(since_iso, until_iso, strategy_id)}


@router.get("/api/paper-trading/coin-stats/{strategy_id}")
def get_coin_stats_for_strategy(strategy_id: str, period: str = "all"):
    since_iso, until_iso = _period_bounds(period)
    return {"coins": storage.list_paper_coin_stats_by_strategy(strategy_id, since_iso, until_iso)}


@router.get("/api/paper-trading/alerts")
def get_alerts(limit: int = 30):
    return {"alerts": storage.list_paper_alerts(limit=limit)}


# --------------------------------------------------------------- Group 3: self-learning foundation

@router.get("/api/paper-trading/pattern-memory")
def get_pattern_memory(strategy_id: Optional[str] = None):
    return {"patterns": storage.list_paper_coin_pattern_memory(strategy_id, since=insights.fresh_session_start())}


@router.get("/api/paper-trading/lesson-candidates")
def get_lesson_candidates():
    """Re-runs the detector at most once per 60s (cached, stale-while-
    revalidate) -- measured ~6s over 1500+ closed trades grouped 4 ways,
    too slow to redo on every single page load. Never applies a candidate
    automatically -- review/action happens elsewhere, by a person."""
    def _refresh():
        insights.detect_lesson_candidates()
        return storage.list_paper_lesson_candidates()
    return {"candidates": cache.cached("paper_lesson_candidates", 60, _refresh)}


@router.get("/api/paper-trading/streak/{strategy_id}")
def get_streak(strategy_id: str):
    return insights.compute_streak(strategy_id)


@router.get("/api/paper-trading/genealogy/{strategy_id}")
def get_genealogy(strategy_id: str):
    return {"versions": lib.version_history(strategy_id)}


# --------------------------------------------------------------- Group 4: paper -> real bridge

@router.get("/api/paper-trading/readiness/{strategy_id}")
def get_readiness(strategy_id: str):
    since_iso, until_iso = _period_bounds("all")
    strategy_stats = next(
        (s for s in storage.list_paper_strategy_stats(since_iso, until_iso) if s["strategy_id"] == strategy_id),
        {"closed_trades": 0, "win_rate": 0.0},
    )
    try:
        cfg = lib.load(strategy_id)
        safety_passed = run_safety_check(cfg)["passed"] and not validator.validate(cfg)
    except Exception:
        safety_passed = False
    meta = next((m for m in lib.list_all() if m["id"] == strategy_id), {})
    wf_status = meta.get("walk_forward_status")
    return insights.real_trading_readiness(strategy_id, strategy_stats, safety_passed, wf_status)


# --------------------------------------------------------------- Self-Learning Activation: Auto-Avoid

@router.get("/api/paper-trading/auto-avoid-rules")
def get_auto_avoid_rules(active_only: bool = True):
    return {"rules": storage.list_paper_auto_avoid_rules(active_only=active_only)}


@router.post("/api/paper-trading/auto-avoid-rules/{rule_id}/deactivate")
def deactivate_auto_avoid_rule(rule_id: int):
    storage.deactivate_paper_auto_avoid_rule(rule_id, datetime.now(timezone.utc).isoformat())
    _log_and_broadcast(f"[paper-trading] auto-avoid rule #{rule_id} deactivated by a person")
    sync.notify("paper_trading", "updated", "Auto-avoid rule deactivated", id=str(rule_id))
    return {"ok": True}


# --------------------------------------------------------------- Self-Learning Activation: Auto-Lessons

@router.get("/api/paper-trading/auto-lessons")
def get_auto_lessons(active_only: bool = True):
    return {"lessons": storage.list_paper_auto_lessons(active_only=active_only)}


@router.post("/api/paper-trading/auto-lessons/{lesson_id}/deactivate")
def deactivate_auto_lesson(lesson_id: int):
    storage.deactivate_paper_auto_lesson(lesson_id, datetime.now(timezone.utc).isoformat())
    _log_and_broadcast(f"[paper-trading] auto-applied lesson #{lesson_id} deactivated by a person")
    sync.notify("paper_trading", "updated", "Auto-lesson deactivated", id=str(lesson_id))
    return {"ok": True}


# --------------------------------------------------------------- Drawdown Protection Engine

@router.get("/api/paper-trading/paused-strategies")
def get_paused_strategies():
    return {"paused": storage.list_paused_strategies()}


@router.post("/api/paper-trading/resume/{strategy_id}")
def resume_strategy(strategy_id: str):
    drawdown_guard.resume_strategy(strategy_id)
    _log_and_broadcast(f"[paper-trading] {strategy_id} resumed (Drawdown Protection pause cleared) by a person")
    sync.notify("paper_trading", "updated", "Strategy resumed", id=strategy_id)
    return {"ok": True}


# --------------------------------------------------------------- Basic Risk Analytics

@router.get("/api/paper-trading/risk-metrics/{strategy_id}")
def get_risk_metrics(strategy_id: str):
    return insights.compute_risk_metrics(strategy_id, since=insights.fresh_session_start())


# --------------------------------------------------------------- Basic Market Regime Detection

@router.get("/api/paper-trading/regime")
def get_market_regime():
    """Bulk regime classification for every tracked symbol -- cached 60s
    (stale-while-revalidate, same pattern as /api/home) since it's a
    50-symbol ATR/MA pass, not free to redo on every poll."""
    exchanges_cfg = base_config.load_or_seed("exchanges.json", base_config.DEFAULTS["exchanges.json"])
    exchange = exchanges_cfg["default"]
    symbols = storage.load_symbols(exchange)

    def _compute():
        return regime.classify_all(exchange, symbols)
    return {"exchange": exchange, "regimes": cache.cached(f"market_regime_{exchange}", 60, _compute)}


@router.get("/api/paper-trading/regime/{symbol}")
def get_symbol_regime(symbol: str):
    exchanges_cfg = base_config.load_or_seed("exchanges.json", base_config.DEFAULTS["exchanges.json"])
    exchange = exchanges_cfg["default"]
    result = regime.classify_regime(exchange, symbol)
    if result is None:
        raise HTTPException(404, "not enough data yet for this symbol")
    return result
