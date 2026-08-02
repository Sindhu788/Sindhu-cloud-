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
from paper_trading import drawdown_guard, regime, correlation, portfolio, strategy_profile, weekly_report
from paper_trading import confluence, graveyard, telegram_bot, capital_allocation, ai_trade_review
from paper_trading import telegram_analytics
from paper_trading import pattern_stats
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


class ResetBalanceRequest(BaseModel):
    confirm: bool = False


@router.get("/api/paper-trading/reset-balance/preview")
def preview_reset_balance():
    """What the confirmation dialog shows before the CEO commits -- real
    numbers, not a generic warning, so the plain-language explanation of
    "what will and will not be affected" (Batch 4, Task 2) is backed by
    the actual current state."""
    settings = pt_config.load()
    initial_balance = settings.get("initial_balance", 10000.0)
    states = storage.list_paper_account_states()
    open_positions = storage.get_open_paper_positions()
    return {
        "current_combined_balance": round(initial_balance * len(states) + sum(s["realized_pnl_total"] for s in states), 2),
        "reset_combined_balance": round(initial_balance * len(states), 2),
        "initial_balance": initial_balance,
        "strategies_affected": len(states),
        "closed_trades_preserved": sum(s["closed_count"] for s in states),
        "open_positions_left_running": len(open_positions),
    }


@router.post("/api/paper-trading/reset-balance")
def reset_balance(req: ResetBalanceRequest):
    """Batch 4, Task 2 -- resets every strategy's working balance back to
    its configured initial_balance. Deliberately does NOT touch closed
    trade history, lessons, evolution data, or strategy performance
    stats (storage.reset_paper_balance only zeroes realized_pnl_total,
    never closed_count/win_count/paper_positions). Open positions are
    left running, not force-closed -- they don't factor into the balance
    figure until they close (see paper_trading.engine.status()), so a
    reset can never leave the balance inconsistent with what they're
    holding; once they do close, their real PnL lands on top of the
    fresh baseline exactly like any trade opened after the reset."""
    if not req.confirm:
        raise HTTPException(400, "Confirmation required -- pass confirm: true to reset the balance.")
    now = datetime.now(timezone.utc).isoformat()
    summary = storage.reset_paper_balance(now)
    cache.invalidate("home_account_snapshot")
    sync.notify("paper_trading", "balance_reset",
                f"Paper Trading balance reset for {summary['strategies_reset']} strategy book(s)")
    _log_and_broadcast(
        f"[paper-trading] Balance reset: {summary['strategies_reset']} strategy book(s) zeroed "
        f"(previous combined realized PnL {summary['previous_total_realized_pnl']:.2f}), "
        f"{summary['open_positions_left_running']} open position(s) left running untouched."
    )
    return {"ok": True, **summary}


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


@router.get("/api/paper-trading/strategy-comparison/export")
def export_strategy_comparison(period: str = "all"):
    """Strategy Comparison -- Export (Remaining Dashboard Enhancements,
    item 4): the exact same per_strategy rows the Strategy Comparison
    table on the dashboard already shows, written out as a real .xlsx
    using openpyxl (already a project dependency, same pattern
    backtest_engine/export.py's export_excel already uses) -- no new
    computation, purely a different output format of the same data."""
    import io
    import pandas as pd
    from fastapi.responses import StreamingResponse

    analytics = _compute_analytics(period)
    rows = [
        {
            "Strategy": p.get("strategy_name") or p.get("strategy_id"),
            "Balance": p.get("balance"),
            "Closed Trades": p.get("closed_trades"),
            "Win Rate %": p.get("win_rate"),
            "Total PnL": p.get("total_pnl"),
            "Confidence Score": p.get("confidence_score"),
        }
        for p in analytics.get("per_strategy", [])
    ]
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, sheet_name="Strategy Comparison", index=False)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=strategy_comparison_{period}.xlsx"},
    )


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
    """Manual Override (A2): flag this strategy for a Telegram alert
    regardless of its automatic score, and genuinely SEND a real message
    for that strategy's most recent open position -- not just an internal
    flag. If no Telegram bot is configured yet, or there's no open
    position, this is reported honestly (send_result), never silently."""
    now = datetime.now(timezone.utc).isoformat()
    storage.save_paper_strategy_override(strategy_id, req.manual_alert, req.note, now)
    send_result = None
    if req.manual_alert:
        _log_and_broadcast(f"[paper-trading] MANUAL OVERRIDE: {strategy_id} flagged for Telegram alert"
                            + (f" -- {req.note}" if req.note else ""))
        open_positions = [p for p in storage.get_open_paper_positions() if p.get("strategy_id") == strategy_id]
        if open_positions:
            most_recent = max(open_positions, key=lambda p: p["entry_time"])
            send_result = telegram_bot.send_signal_for_position(most_recent["id"], trigger_type="manual")
            _log_and_broadcast(f"[paper-trading] Telegram send for {strategy_id}: "
                                f"{'sent' if send_result['ok'] else 'FAILED - ' + str(send_result.get('error'))}")
        else:
            send_result = {"ok": False, "error": "no open position for this strategy right now"}
    sync.notify("paper_trading", "updated", "Manual override updated", id=strategy_id)
    return {"ok": True, "override": storage.get_paper_strategy_override(strategy_id), "telegram_send_result": send_result}


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


@router.get("/api/paper-trading/balance-history/{strategy_id}")
def get_balance_history(strategy_id: str, limit: int = 500):
    """Fake Money Balance History (Remaining Dashboard Enhancements, item 1):
    a real time-series of a strategy's own virtual balance, not just the
    current number -- built from the same closed-trade PnL history and
    Capital Allocation multiplier every other balance figure on this
    dashboard already uses (paper_trading.risk_manager.account_balance),
    just walked forward point-by-point instead of read once at the end."""
    settings = pt_config.load()
    initial_balance = settings.get("initial_balance", 10000.0)
    multiplier, _ = storage.get_strategy_capital_multiplier(strategy_id)
    trades = storage.list_paper_closed_trades_ordered(strategy_id=strategy_id, limit=limit)

    # Batch 4, Task 2: after a Reset Balance, realized_pnl_total is zeroed
    # but paper_positions (this trade history) is deliberately never
    # touched -- so without this, the graph would replay every pre-reset
    # trade into a running total that no longer matches the live (reset)
    # balance anywhere else in the app. Clip to trades closed after the
    # most recent reset for this book so the graph starts fresh from the
    # same point the real balance did, while the trades themselves stay
    # fully intact in the database for audit.
    last_reset_at = storage.get_last_balance_reset_at(strategy_id)
    if last_reset_at:
        trades = [t for t in trades if t["closed_at"] and t["closed_at"] > last_reset_at]

    base = initial_balance * multiplier
    points = [{"at": last_reset_at, "balance": round(base, 2)}]
    running = base
    for t in trades:
        running += (t["pnl"] or 0.0)
        points.append({"at": t["closed_at"], "balance": round(running, 2)})
    return {"strategy_id": strategy_id, "initial_balance": round(base, 2), "points": points}


@router.get("/api/paper-trading/confluence-history/{strategy_id}")
def get_confluence_history(strategy_id: str, limit: int = 100):
    """Historical Confluence Score Tracking (Remaining Dashboard
    Enhancements, item 5): how a strategy's average Confluence Score has
    trended over time, not just its current value -- reads the log
    written at signal time (see paper_trading.engine._open_if_allowed)."""
    return {"strategy_id": strategy_id, "history": storage.list_confluence_history(strategy_id, limit=limit)}


@router.get("/api/paper-trading/pattern-reliability")
def get_pattern_reliability(strategy_id: Optional[str] = None):
    """Genuine Evolution Engine (statistically-sound lessons): for every
    real (strategy, coin, market regime, session) combination seen this
    session, shows the current sample size, whether it has crossed the
    reliability threshold (pattern_stats.MIN_SAMPLE_SIZE, currently 25
    trades), and -- once reliable -- the Wilson 95% confidence interval
    and conclusion this is judged on. This is the exact same calculation
    Pattern Auto-Avoid and Lesson Auto-Apply act on, just made visible."""
    patterns = storage.list_paper_coin_pattern_memory(strategy_id, since=insights.fresh_session_start())
    rows = []
    for p in patterns:
        result = pattern_stats.classify(p["wins"], p["trades"])
        rows.append({
            "strategy_id": p["strategy_id"], "strategy_name": p["strategy_name"],
            "symbol": p["symbol"], "market_state": p["market_state"], "session": p["session"],
            "total_pnl": p["total_pnl"], **result,
        })
    rows.sort(key=lambda r: r["sample_size"], reverse=True)
    return {
        "min_sample_size": pattern_stats.MIN_SAMPLE_SIZE,
        "method": "wilson_score_95",
        "patterns": rows,
    }


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
    """Strategy Genealogy used to show ONLY manual config-save versions --
    a person clicking "History" to understand why a strategy's behavior
    changed would see nothing about Pattern Auto-Avoid or Lesson
    Auto-Apply ever kicking in, even though those are exactly the kind of
    behavioral change genealogy exists to explain. Merges those events
    into the same chronological timeline (no schema change needed -- the
    statistical evidence, sample size and Wilson confidence interval, is
    already embedded in each rule/lesson's own reason/explanation text)."""
    versions = lib.version_history(strategy_id)
    events = [{"type": "version_saved", "at": v["modified_at"], "detail": f"Version {v['version']} saved"}
              for v in versions]

    for rule in storage.list_paper_auto_avoid_rules():
        if rule["strategy_id"] != strategy_id:
            continue
        events.append({
            "type": "auto_avoid_triggered", "at": rule["triggered_at"],
            "detail": rule["reason"], "symbol": rule["symbol"],
        })
        if rule["deactivated_at"]:
            events.append({
                "type": "auto_avoid_cleared", "at": rule["deactivated_at"],
                "detail": f"Auto-Avoid rule for {rule['symbol']} ({rule['market_state']}/{rule['session']}) "
                          f"no longer active -- pattern is no longer a statistically confident loser.",
                "symbol": rule["symbol"],
            })

    for lesson in storage.list_paper_auto_lessons():
        if lesson["strategy_id"] != strategy_id:
            continue
        events.append({
            "type": "auto_lesson_applied", "at": lesson["applied_at"],
            "detail": lesson["explanation"], "symbol": lesson["symbol"],
        })
        if lesson["deactivated_at"]:
            events.append({
                "type": "auto_lesson_cleared", "at": lesson["deactivated_at"],
                "detail": f"Auto-Lesson for {lesson['symbol']} ({lesson['market_state']}/{lesson['session']}) "
                          f"no longer active -- pattern drifted back to inconclusive.",
                "symbol": lesson["symbol"],
            })

    events.sort(key=lambda e: e["at"] or "", reverse=True)
    return {"versions": versions, "timeline": events}


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


@router.get("/api/paper-trading/ai-trade-review/settings")
def get_ai_trade_review_settings():
    return {"enabled": ai_trade_review.is_enabled()}


class AiReviewToggle(BaseModel):
    enabled: bool


@router.post("/api/paper-trading/ai-trade-review/settings")
def set_ai_trade_review_settings(req: AiReviewToggle):
    ai_trade_review.set_enabled(req.enabled)
    return {"ok": True, "enabled": req.enabled}


@router.get("/api/paper-trading/ai-trade-review/{position_id}")
def get_ai_trade_review(position_id: str):
    review = storage.get_trade_review(position_id)
    if review is None:
        raise HTTPException(404, "no review for this trade yet")
    return review


@router.get("/api/paper-trading/capital-allocations")
def get_capital_allocations():
    return {"allocations": storage.list_capital_allocations()}


@router.post("/api/paper-trading/capital-allocations/recompute-now")
def recompute_capital_allocations_now():
    return {"updated": capital_allocation.recompute_all_allocations()}


@router.get("/api/paper-trading/risk-metrics-all")
def get_risk_metrics_all():
    """Bulk version for a table view (Strategy Performance Dashboard) --
    one call instead of one per strategy. All reads are cheap indexed DB
    queries (no network), so a loop here is fine unlike coin_filter's
    per-symbol exchange calls."""
    since = insights.fresh_session_start()
    out = {}
    for meta in lib.list_all():
        out[meta["id"]] = insights.compute_risk_metrics(meta["id"], since=since)
    return {"metrics": out}


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


# --------------------------------------------------------------- Correlation Warning System

@router.get("/api/paper-trading/correlation-warnings")
def get_correlation_warnings():
    """Informational only -- cached 60s (same stale-while-revalidate
    pattern used throughout this file) since it's a pairwise price-history
    comparison, not free to redo on every dashboard poll."""
    exchanges_cfg = base_config.load_or_seed("exchanges.json", base_config.DEFAULTS["exchanges.json"])
    exchange = exchanges_cfg["default"]

    def _compute():
        return correlation.detect_warnings(exchange)
    return {"warnings": cache.cached(f"correlation_warnings_{exchange}", 60, _compute)}


# --------------------------------------------------------------- Portfolio & Capital Intelligence

@router.get("/api/paper-trading/portfolio")
def get_portfolio_analytics():
    """Cached 60s -- compute_portfolio_analytics() calls correlation.detect_warnings()
    internally, the same 60s+-cold pairwise price comparison the dedicated
    correlation-warnings endpoint already caches; without caching here too,
    every /portfolio poll would silently repeat that full cost."""
    exchanges_cfg = base_config.load_or_seed("exchanges.json", base_config.DEFAULTS["exchanges.json"])
    exchange = exchanges_cfg["default"]

    def _compute():
        return portfolio.compute_portfolio_analytics(exchange)
    return cache.cached(f"portfolio_analytics_{exchange}", 60, _compute)


@router.get("/api/paper-trading/portfolio-risk-score")
def get_portfolio_risk_score():
    strategy_ids = [m["id"] for m in lib.list_all()]
    return portfolio.compute_portfolio_risk_score(strategy_ids, since=insights.fresh_session_start())


@router.get("/api/paper-trading/coin-exposure")
def get_coin_exposure():
    exchanges_cfg = base_config.load_or_seed("exchanges.json", base_config.DEFAULTS["exchanges.json"])
    exchange = exchanges_cfg["default"]
    return {"exposure": portfolio.compute_coin_exposure(exchange)}


# --------------------------------------------------------------- Trade Audit Engine (Group 6 #5)

@router.get("/api/paper-trading/strategy-profile/{strategy_id}")
def get_strategy_profile_endpoint(strategy_id: str):
    exchanges_cfg = base_config.load_or_seed("exchanges.json", base_config.DEFAULTS["exchanges.json"])
    exchange = exchanges_cfg["default"]
    # Reuse the same 60s cache correlation-warnings/portfolio already warm
    # -- avoids re-running the ~60s-cold pairwise price comparison on every
    # Profile click (the same bug class fixed in portfolio.py earlier).
    warnings = cache.cached(f"correlation_warnings_{exchange}", 60, lambda: correlation.detect_warnings(exchange))
    profile = strategy_profile.get_strategy_profile(strategy_id, exchange, correlation_warnings=warnings)
    if profile is None:
        raise HTTPException(404, "strategy not found")
    return profile


# --------------------------------------------------------------- Telegram Integration (Section A)

class TelegramSettingsUpdate(BaseModel):
    bot_token: Optional[str] = None
    channel_id: Optional[str] = None
    master_send_enabled: Optional[bool] = None
    auto_send_enabled: Optional[bool] = None
    auto_send_min_confluence_ratio: Optional[float] = None
    rate_limit_per_hour: Optional[int] = None
    send_close_followups: Optional[bool] = None
    proxy_enabled: Optional[bool] = None
    proxy_url: Optional[str] = None


@router.get("/api/paper-trading/telegram/settings")
def get_telegram_settings():
    """Never returns the raw bot token -- only whether one is configured."""
    return telegram_bot.public_settings()


@router.post("/api/paper-trading/telegram/settings")
def update_telegram_settings(req: TelegramSettingsUpdate):
    telegram_bot.save_settings(**req.dict(exclude_unset=True))
    note = ""
    if req.master_send_enabled is not None:
        note += " (Telegram sending turned " + ("ON" if req.master_send_enabled else "OFF") + ")"
    if req.auto_send_enabled is not None:
        note += " (auto-send " + ("ENABLED" if req.auto_send_enabled else "disabled") + ")"
    _log_and_broadcast("[paper-trading] Telegram settings updated" + note)
    return {"ok": True, "settings": telegram_bot.public_settings()}


@router.post("/api/paper-trading/telegram/test")
def send_telegram_test():
    """A1: real connection confirmation, not simulated."""
    return telegram_bot.send_test_message()


@router.post("/api/paper-trading/telegram/test-proxy")
def test_telegram_proxy():
    """Isolates "is my proxy server reachable at all" from "can it reach
    Telegram specifically" -- checks the configured proxy against a
    plain, unrelated internet endpoint (no bot token/channel needed)."""
    return telegram_bot.test_proxy_connectivity()


@router.get("/api/paper-trading/telegram/log")
def get_telegram_log(limit: int = 50):
    return {"messages": storage.list_telegram_messages(limit=limit)}


@router.get("/api/paper-trading/telegram/alert-status")
def get_telegram_alert_status():
    """(Batch 2, Task 3) Whether 24+ hours have passed since the last
    Telegram signal (any tier) -- backs the dashboard's no-signal alert,
    shared by the Overview page and the Telegram Signals page."""
    return telegram_bot.no_signal_alert_status()


@router.post("/api/paper-trading/telegram/send/{position_id}")
def send_telegram_for_position(position_id: str):
    """On-demand real send for any specific position -- used by A6's
    end-to-end verification with real current Paper Trading data."""
    return telegram_bot.send_signal_for_position(position_id, trigger_type="manual")


# --------------------------------------------------------------- Task C: Telegram Dashboard page

@router.get("/api/paper-trading/telegram/signals")
def list_telegram_signals(period: str = "all"):
    """Every real signal sent to Telegram in this period, with its real
    outcome joined in (win/loss/breakeven/pending) -- backs the Telegram
    Dashboard page's signal log table. Same period vocabulary as Paper
    Trading Analytics (today/yesterday/week/month/all)."""
    since_iso, until_iso = _period_bounds(period)
    return {"signals": storage.list_telegram_signal_outcomes(since_iso, until_iso)}


@router.get("/api/paper-trading/telegram/analytics")
def get_telegram_analytics(period: str = "all"):
    """Period summary + per-strategy breakdown for the Telegram Dashboard
    page -- reuses the same closed-trade outcome data Paper Trading
    Analytics already tracks (paper_positions.status/pnl), just filtered
    to positions that actually had a signal sent to Telegram."""
    since_iso, until_iso = _period_bounds(period)
    return {
        "summary": telegram_analytics.signal_period_summary(since_iso, until_iso),
        "strategy_breakdown": telegram_analytics.strategy_breakdown(since_iso, until_iso),
        "hypothetical_pnl": telegram_analytics.hypothetical_pnl(since_iso, until_iso),
    }


@router.get("/api/paper-trading/confluence/{position_id}")
def get_confluence_for_position(position_id: str):
    """Retroactive confluence score for a real (open or closed) position --
    uses the exact strategy/symbol/market_state/session/direction that
    signal actually fired under."""
    pos = storage.get_paper_position(position_id)
    if not pos:
        raise HTTPException(404, "position not found")
    exchanges_cfg = base_config.load_or_seed("exchanges.json", base_config.DEFAULTS["exchanges.json"])
    exchange = exchanges_cfg["default"]
    return confluence.score_confluence(
        pos.get("strategy_id"), pos["symbol"], exchange,
        pos.get("market_state"), pos.get("session"), pos["direction"],
    )


@router.get("/api/paper-trading/graveyard")
def get_graveyard():
    return {"graveyard": storage.list_graveyard()}


class SimilarityCheck(BaseModel):
    concepts_used: list[str] = []


@router.post("/api/paper-trading/graveyard/check-similarity")
def check_graveyard_similarity(req: SimilarityCheck):
    return {"warnings": graveyard.check_similarity_warnings(req.concepts_used)}


@router.get("/api/paper-trading/weekly-reports")
def get_weekly_reports(limit: int = 20):
    return {"reports": storage.list_weekly_reports(limit=limit)}


@router.post("/api/paper-trading/weekly-reports/generate-now")
def generate_weekly_report_now():
    """Manual trigger, bypassing the 7-day gate -- for testing/on-demand use."""
    result = weekly_report.generate_weekly_report()
    return {"ok": True, "report_text": result["report_text"]}


@router.get("/api/paper-trading/trade-audit/{position_id}")
def get_paper_trade_audit(position_id: str):
    """Full manual-verification detail for one Paper Trading position --
    entry/exit price+time, the exact rule that fired (entry_reason,
    already recorded at open time), the market snapshot at entry, and raw
    1-minute candles spanning the trade for a person to check by hand."""
    from data_engine.resample import get_ohlcv

    pos = storage.get_paper_position(position_id)
    if not pos:
        raise HTTPException(404, "position not found")

    end_reference = pos.get("exit_time") or pos["entry_time"]
    start_ms = pos["entry_time"] - 30 * 60 * 1000
    end_ms = end_reference + 30 * 60 * 1000
    try:
        df = get_ohlcv(pos["exchange"], pos["symbol"], interval="1m", start_ms=start_ms, end_ms=end_ms)
        candles = [
            {"time": int(idx.timestamp() * 1000), "open": row.open, "high": row.high,
             "low": row.low, "close": row.close, "volume": row.volume}
            for idx, row in df.iterrows()
        ]
    except Exception:
        candles = []

    return {"position": pos, "candles": candles}
