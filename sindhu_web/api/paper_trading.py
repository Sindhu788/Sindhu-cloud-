from datetime import datetime, timedelta, timezone
from typing import Optional

import os

from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, FileResponse
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
from paper_trading import telegram_delivery
from paper_trading import signal_tracker
from paper_trading import pattern_stats
from paper_trading import challenge_mode
from paper_trading import cloud_sync
from paper_trading import signal_explainer
from paper_trading import kill_switch, account_drawdown_guard, coin_heatmap, custom_alerts
from paper_trading import trade_journal_export
from paper_trading import coin_blacklist
from paper_trading import position_size_calculator
from paper_trading import health_check
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


@router.get("/api/paper-trading/health-check")
def get_health_check():
    return health_check.run_health_check()


@router.post("/api/paper-trading/start")
def start_engine():
    try:
        started = engine.start(log=_log_and_broadcast, on_event=_on_engine_event)
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    if not started:
        raise HTTPException(400, "engine already running")
    # Batch 9, Task 3: persist this explicit choice immediately (not just
    # on a clean shutdown) so a restart -- including an ungraceful one --
    # restores the engine to ON.
    pt_config.update(engine_enabled=True)
    sync.notify("paper_trading", "started", "Paper Trading engine started")
    return {"ok": True}


@router.post("/api/paper-trading/stop")
def stop_engine():
    stopped = engine.stop()
    if not stopped:
        raise HTTPException(400, "engine already stopped")
    pt_config.update(engine_enabled=False)
    sync.notify("paper_trading", "stopped", "Paper Trading engine stopped")
    return {"ok": True}


class KillSwitchActivateRequest(BaseModel):
    reason: Optional[str] = None
    close_positions: bool = True
    actor: str = "CEO"


@router.get("/api/paper-trading/kill-switch/status")
def kill_switch_status():
    return kill_switch.status()


@router.post("/api/paper-trading/kill-switch/activate")
def kill_switch_activate(req: KillSwitchActivateRequest):
    return kill_switch.activate(reason=req.reason, actor=req.actor, close_positions=req.close_positions)


class KillSwitchDeactivateRequest(BaseModel):
    actor: str = "CEO"


@router.post("/api/paper-trading/kill-switch/deactivate")
def kill_switch_deactivate(req: KillSwitchDeactivateRequest = KillSwitchDeactivateRequest()):
    result = kill_switch.deactivate(actor=req.actor)
    if not result["ok"]:
        raise HTTPException(400, result["error"])
    return result


@router.get("/api/paper-trading/account-drawdown-status")
def account_drawdown_status():
    return account_drawdown_guard.status()


class AccountDrawdownResumeRequest(BaseModel):
    actor: str = "CEO"


@router.post("/api/paper-trading/account-drawdown-resume")
def account_drawdown_resume(req: AccountDrawdownResumeRequest = AccountDrawdownResumeRequest()):
    account_drawdown_guard.resume_account(actor=req.actor)
    return account_drawdown_guard.status()


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
    time_filter_enabled: Optional[bool] = None
    time_filter_block_start_utc: Optional[str] = None
    time_filter_block_end_utc: Optional[str] = None
    profit_lock_enabled: Optional[bool] = None
    profit_lock_trigger_r: Optional[float] = None
    profit_lock_trail_pct: Optional[float] = None
    ensemble_voting_min_agreeing_strategies: Optional[int] = None


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


class TradeNoteRequest(BaseModel):
    note: str = ""


@router.post("/api/paper-trading/positions/{position_id}/note")
def set_trade_note(position_id: str, req: TradeNoteRequest):
    """Grand Feature Expansion, Phase 4 Feature 8: Trade Annotation --
    works on an open OR closed position, never touches pnl/exit/reflection."""
    if not storage.get_paper_position(position_id):
        raise HTTPException(404, "position not found")
    storage.set_trade_note(position_id, req.note)
    return {"ok": True, "note": req.note}


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
    action = "activated" if req.enabled else "deactivated (manual override)"
    _log_and_broadcast(f"[paper-trading] {strategy_id} {action} by a person")
    sync.notify("paper_trading", "updated", "Paper strategy config updated", id=strategy_id)
    return {"ok": True}


# --------------------------------------------------- Master Task 2, Part 3
# Advanced per-strategy controls: manual pause/resume, full stats reset
# (archived, not deleted), and risk%/max-open-positions overrides.

@router.post("/api/paper-trading/strategy-config/{strategy_id}/pause")
def pause_strategy_manual(strategy_id: str):
    """Manual pause -- same underlying flag as Drawdown Protection's
    automatic pause (storage.is_strategy_paused, checked in
    engine._open_if_allowed before every new entry), so it stops new
    entries immediately while leaving existing open positions alone. The
    reason text is what distinguishes "a person chose this" from an
    automatic drawdown pause on the dashboard."""
    storage.set_strategy_paused(strategy_id, True, "Paused manually by a person",
                                 datetime.now(timezone.utc).isoformat())
    _log_and_broadcast(f"[paper-trading] {strategy_id} paused manually by a person")
    sync.notify("paper_trading", "updated", "Strategy paused", id=strategy_id)
    return {"ok": True}


@router.post("/api/paper-trading/strategy-config/{strategy_id}/resume")
def resume_strategy_manual(strategy_id: str):
    """Same action as the existing Drawdown Protection "Resume" button
    (/api/paper-trading/resume/{id}) -- exposed here too so every Advanced
    Control for a strategy lives under one consistent URL prefix."""
    drawdown_guard.resume_strategy(strategy_id)
    _log_and_broadcast(f"[paper-trading] {strategy_id} resumed by a person")
    sync.notify("paper_trading", "updated", "Strategy resumed", id=strategy_id)
    return {"ok": True}


class RiskOverrideUpdate(BaseModel):
    risk_pct_override: Optional[float] = None
    max_open_trades_override: Optional[int] = None


@router.post("/api/paper-trading/strategy-config/{strategy_id}/overrides")
def update_strategy_overrides(strategy_id: str, req: RiskOverrideUpdate):
    """None clears an override back to "use the global default". Bounded --
    an override can narrow or widen this one strategy's risk, but never to
    something unsafe (0%/negative risk, or an effectively unlimited coin
    cap)."""
    if req.risk_pct_override is not None and not (0 < req.risk_pct_override <= 10):
        raise HTTPException(400, "risk_pct_override must be between 0 and 10 (percent)")
    if req.max_open_trades_override is not None and not (1 <= req.max_open_trades_override <= 20):
        raise HTTPException(400, "max_open_trades_override must be between 1 and 20")
    storage.set_strategy_risk_overrides(
        strategy_id, req.risk_pct_override, req.max_open_trades_override,
        datetime.now(timezone.utc).isoformat(),
    )
    _log_and_broadcast(f"[paper-trading] {strategy_id} risk overrides updated by a person: "
                        f"risk_pct={req.risk_pct_override}, max_open_trades={req.max_open_trades_override}")
    sync.notify("paper_trading", "updated", "Strategy risk overrides updated", id=strategy_id)
    return {"ok": True, **storage.get_paper_strategy_config(strategy_id)}


class StrategyResetRequest(BaseModel):
    confirm: bool = False


@router.get("/api/paper-trading/strategy-config/{strategy_id}/reset-stats/preview")
def preview_strategy_stats_reset(strategy_id: str):
    settings = pt_config.load()
    initial_balance = settings.get("initial_balance", 10000.0)
    summary = storage.get_paper_account_summary(strategy_id)
    open_count = len(storage.get_open_paper_position_symbols(strategy_id))
    return {
        "strategy_id": strategy_id,
        "current_balance": round(initial_balance + summary["realized_pnl_total"], 2),
        "current_closed_trades": summary["closed_count"],
        "current_win_count": summary["win_count"],
        "open_positions_left_running": open_count,
    }


@router.post("/api/paper-trading/strategy-config/{strategy_id}/reset-stats")
def reset_strategy_stats(strategy_id: str, req: StrategyResetRequest):
    """Per-strategy version of /api/paper-trading/reset-balance -- resets
    THIS strategy's balance AND win/loss counters back to a fresh start,
    archiving the previous numbers (never deleting them) in
    paper_strategy_stat_archives. paper_positions (this strategy's real
    trade-by-trade history) is untouched; only the live aggregate counters
    reset. Open positions keep running."""
    if not req.confirm:
        raise HTTPException(400, "Confirmation required -- pass confirm: true to reset this strategy's stats.")
    summary = storage.reset_strategy_stats(strategy_id, datetime.now(timezone.utc).isoformat())
    cache.invalidate("home_account_snapshot")
    _log_and_broadcast(
        f"[paper-trading] {strategy_id} stats reset by a person (previous realized PnL "
        f"{summary['previous_realized_pnl_total']:.2f}, {summary['previous_closed_count']} closed trades archived, "
        f"{summary['open_positions_left_running']} open position(s) left running untouched)."
    )
    sync.notify("paper_trading", "stats_reset", "Strategy stats reset", id=strategy_id)
    return {"ok": True, **summary}


@router.get("/api/paper-trading/strategy-config/{strategy_id}/reset-history")
def get_strategy_reset_history(strategy_id: str):
    return {"archives": storage.list_strategy_stat_archives(strategy_id)}


# The period vocabulary every period-aware endpoint on this router shares.
# Order matters -- the dashboard renders its selector straight from this
# list, so adding a period here is the only change needed to offer it.
#
# "7d"/"15d"/"30d" are ROLLING windows (the last N complete days plus
# today), not calendar buckets: "last 7 days" on a Wednesday means the
# previous Thursday onward, which is what a person actually means by it.
# "week"/"month" are the older CALENDAR buckets (this calendar week /
# this calendar month) and are kept unchanged so existing links,
# bookmarks, and the Project Status page keep working exactly as before.
PERIODS = [
    ("today", "Today"),
    ("yesterday", "Yesterday"),
    ("7d", "Last 7 Days"),
    ("15d", "Last 15 Days"),
    ("30d", "Last 1 Month"),
    ("all", "All-Time"),
]

_ROLLING_DAYS = {"7d": 7, "15d": 15, "30d": 30}


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
    if period in _ROLLING_DAYS:
        # N-1 because the window INCLUDES today: "last 7 days" is today
        # plus the 6 days before it, not today plus 7 more.
        start = today_start - timedelta(days=_ROLLING_DAYS[period] - 1)
        return start.isoformat(), None
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

    # Best/worst strategy IN THIS PERIOD -- deliberately restricted to
    # strategies that actually closed at least one trade inside the window.
    # strategy_stats also carries strategies with zero closed trades (newly
    # enabled, or only open positions so far); calling one of those "worst
    # performing" because its $0.00 sorts below a losing strategy would be
    # a false statement about a strategy that has not traded yet.
    traded = [s for s in strategy_stats if s["closed_trades"] > 0]
    traded_sorted = sorted(traded, key=lambda s: s["total_pnl"], reverse=True)

    def _headline(row):
        if not row:
            return None
        return {
            "strategy_id": row["strategy_id"],
            "strategy_name": row["strategy_name"],
            "total_pnl": round(row["total_pnl"], 2),
            "closed_trades": row["closed_trades"],
            "win_rate": row["win_rate"],
        }

    # Combined current balance across every independent strategy book.
    # This is a CURRENT figure, not a period one -- a balance is a
    # point-in-time fact, so it reads the same whichever period is
    # selected. Labelled that way in the UI rather than left ambiguous.
    initial = initial_balance
    current_balance = round(
        initial * len(account_states) + sum(a["realized_pnl_total"] for a in account_states.values()),
        2,
    ) if account_states else 0.0

    # Wins/losses as explicit counts. summary already carries wins; a
    # "loss" here means a closed trade that finished below breakeven, so
    # closed - wins would silently fold break-even trades into losses.
    losses = max(summary["closed_trades"] - summary["win_count"], 0) if "win_count" in summary else None

    return {
        "new_alerts": new_alerts,
        "period": period,
        "summary": summary,
        "open_positions_count": len(open_positions),
        "current_balance": current_balance,
        "loss_count": losses,
        "best_strategy": _headline(traded_sorted[0] if traded_sorted else None),
        "worst_strategy": _headline(traded_sorted[-1] if len(traded_sorted) > 1 else None),
        "best_coin": coin_stats[0] if coin_stats else None,
        "worst_coin": coin_stats[-1] if coin_stats else None,
        "per_coin": coin_stats,
        "per_strategy": strategy_stats,
    }


@router.get("/api/paper-trading/strategy-configs")
def list_all_strategy_configs():
    """Every strategy's per-strategy settings in ONE call -- the settings
    table needs enabled/paused/risk-override/max-open-override for all of
    them at once, and fetching them one strategy at a time would be ~40
    round-trips for a single screen (the exact shape of slowness already
    fixed elsewhere on this page)."""
    return {"configs": storage.list_paper_strategy_configs()}


@router.get("/api/paper-trading/strategy-overview")
def get_strategy_overview():
    """Powers the cloud dashboard's "Strategies" page: one row per strategy
    saved in the library, with real numbers -- never placeholders -- for
    win rate, net PnL, and risk:reward, plus whether it's currently active
    in Paper Trading and whether it's currently safe to activate.

    Win rate/PnL/closed trades come from actual Paper Trading history
    (storage.list_paper_strategy_stats), not the backtest engine -- this
    runner's database deliberately excludes the backtest_* tables (see
    data_engine/db_backend.py's own docstring), so live paper-trading
    results are the only real performance numbers available here. A
    strategy with zero paper trades legitimately shows 0/0.0, not a
    rounded-off guess.

    Risk:reward prefers the strategy's own FIXED configured ratio (
    take_profit.type == "rr", or the legacy risk_reward field) when one
    exists; only a strategy whose stop-loss/take-profit are structure-based
    (no single fixed ratio to state) falls back to the average R:R actually
    realized across its live trades (paper_strategy_performance.avg_rr).

    can_activate/activation_blocked_reason reuse the exact same combined
    gate /api/paper-trading/readiness/{id} already uses (the automatic
    Strategy Safety Check plus the config validator) -- a strategy that
    fails either is not safe to run unattended, so the frontend disables
    its Move-to-Paper-Trading button and shows why, rather than silently
    letting it through."""
    metas = lib.list_all()
    configs = storage.list_paper_strategy_configs()
    stats_by_id = {s["strategy_id"]: s for s in storage.list_paper_strategy_stats()}
    perf_by_id = {p["strategy_id"]: p for p in storage.list_paper_strategy_performance()}

    rows = []
    for meta in metas:
        sid = meta["id"]
        cfg_row = configs.get(sid, {})
        stat = stats_by_id.get(sid)
        perf = perf_by_id.get(sid)

        fixed_rr = None
        can_activate = False
        blocked_reason = None
        try:
            cfg = lib.load(sid)
            tp = cfg.take_profit
            if tp and tp.type == "rr" and tp.value:
                fixed_rr = tp.value
            elif cfg.risk_reward:
                fixed_rr = cfg.risk_reward
            errors = validator.validate(cfg)
            safety = run_safety_check(cfg)
            can_activate = bool(safety["passed"]) and not errors
            if not can_activate:
                reasons = list(safety.get("reasons") or []) + list(errors or [])
                blocked_reason = "; ".join(reasons) if reasons else "Failed the automatic Strategy Safety Check."
        except Exception as exc:
            blocked_reason = f"Could not load this strategy's saved configuration ({exc})."

        avg_rr = perf.get("avg_rr") if perf else None
        rows.append({
            "strategy_id": sid,
            "name": meta.get("name", sid),
            "win_rate": stat["win_rate"] if stat else 0.0,
            "closed_trades": stat["closed_trades"] if stat else 0,
            "total_pnl": round(stat["total_pnl"], 2) if stat else 0.0,
            "risk_reward": fixed_rr if fixed_rr is not None else avg_rr,
            "risk_reward_is_fixed": fixed_rr is not None,
            # Master Task 3, Phase 0.7: dual-row Strategies table -- the
            # local machine's most recent backtest numbers (win_rate,
            # profit_factor), refreshed opportunistically by
            # sindhu_web/api/backtesting.py's _compute_strategies_list and
            # carried here via meta.json (git-tracked, so it also reaches
            # the cloud deploy, which has no backtest_* tables of its own).
            # None on a strategy that has never completed a local backtest.
            "backtest": meta.get("backtest_snapshot"),
            "in_paper_trading": bool(cfg_row.get("enabled")),
            "paper_config": {
                "priority": cfg_row.get("priority", 5),
                "supported_coins": cfg_row.get("supported_coins", []),
                "supported_market_types": cfg_row.get("supported_market_types", []),
            },
            "can_activate": can_activate,
            "activation_blocked_reason": blocked_reason,
        })
    return {"strategies": rows}


@router.get("/api/paper-trading/periods")
def get_periods():
    """The single source of truth for which time periods the dashboard
    offers, so the selector and the backend can never drift apart."""
    return {"periods": [{"id": pid, "label": label} for pid, label in PERIODS]}


@router.get("/api/paper-trading/strategy-periods/{strategy_id}")
def get_strategy_periods(strategy_id: str):
    """Every time period at once for ONE strategy -- backs the per-strategy
    drill-down. One request instead of six round-trips, and the numbers are
    guaranteed to come from the same instant rather than from six separate
    moments as the user clicks between periods.

    Scoped strictly to this strategy's own independent book: nothing here
    is blended with, averaged against, or divided by any other strategy."""
    meta = next((m for m in lib.list_all() if m["id"] == strategy_id), None)
    config = storage.get_paper_strategy_config(strategy_id)
    periods = []
    for pid, label in PERIODS:
        since_iso, until_iso = _period_bounds(pid)
        stats = storage.get_paper_strategy_period_stats(strategy_id, since_iso, until_iso)
        stats["period"] = pid
        stats["label"] = label
        periods.append(stats)

    initial_balance = pt_config.load().get("initial_balance", 10000.0)
    acct = next(
        (s for s in storage.list_paper_account_states() if s["strategy_id"] == strategy_id),
        None,
    )
    return {
        "strategy_id": strategy_id,
        "strategy_name": (meta or {}).get("name") or strategy_id,
        # A balance is a point-in-time fact, not a period one -- reported
        # once, outside the period list, so it can never be misread as
        # "the balance during last week".
        "current_balance": round(initial_balance + acct["realized_pnl_total"], 2) if acct else initial_balance,
        "initial_balance": initial_balance,
        "enabled": bool(config.get("enabled")),
        "paused": bool(config.get("paused")),
        "periods": periods,
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


@router.get("/api/paper-trading/cloud-sync/status")
def get_cloud_sync_status():
    """Part 6 (this task): whether the automatic 24h cloud-to-local backup
    (paper_trading.cloud_sync) has ever run, and a quick row-count preview
    -- lets the dashboard show "last synced 3 hours ago" without
    downloading the whole snapshot."""
    snapshot = cloud_sync.get_latest_snapshot()
    if not snapshot:
        return {"has_run": False, "generated_at": None}
    return {
        "has_run": True,
        "generated_at": snapshot["generated_at"],
        "open_positions": len(snapshot["open_positions"]),
        "closed_positions": len(snapshot["closed_positions"]),
        "telegram_signals": len(snapshot["telegram_signal_log"]),
    }


@router.post("/api/paper-trading/cloud-sync/run-now")
def run_cloud_sync_now():
    """Manual trigger -- generates a fresh snapshot immediately rather
    than waiting for the scheduler's own up-to-24h gate, for a CEO who
    wants an up-to-date backup right before pulling it down, or to prove
    the mechanism works without waiting a full day."""
    snapshot = cloud_sync.run_sync()
    return {"ok": True, "generated_at": snapshot["generated_at"]}


@router.get("/api/paper-trading/cloud-sync/download")
def download_cloud_sync_snapshot():
    """Downloads the most recent 24h backup snapshot as a JSON file --
    open positions, closed trades, the Telegram signal log, and per-
    strategy performance stats. One-way (cloud -> local): this endpoint
    only ever reads and hands out the cloud's own data, it never accepts
    or writes anything back."""
    snapshot = cloud_sync.get_latest_snapshot()
    if not snapshot:
        raise HTTPException(
            status_code=404,
            detail="No sync snapshot has been generated yet. It runs automatically "
                   "every 24 hours, or call POST /api/paper-trading/cloud-sync/run-now "
                   "to generate one immediately.",
        )
    filename = f"sindhu_cloud_sync_{snapshot['generated_at'][:10]}.json"
    return JSONResponse(content=jsonable_encoder(snapshot),
                         headers={"Content-Disposition": f"attachment; filename={filename}"})


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


@router.get("/api/paper-trading/hour-of-day-stats")
def get_hour_of_day_stats(strategy_id: Optional[str] = None, period: str = "all"):
    """Grand Feature Expansion, Phase 3 Feature 10: more granular than
    session-stats above (named sessions) -- one row per UTC hour (00-23)."""
    since_iso, until_iso = _period_bounds(period)
    return {"hours": storage.list_paper_hour_of_day_stats(since_iso, until_iso, strategy_id)}


@router.get("/api/paper-trading/coin-stats/{strategy_id}")
def get_coin_stats_for_strategy(strategy_id: str, period: str = "all"):
    since_iso, until_iso = _period_bounds(period)
    return {"coins": storage.list_paper_coin_stats_by_strategy(strategy_id, since_iso, until_iso)}


@router.get("/api/paper-trading/coin-heatmap")
def get_coin_heatmap(period: str = "all"):
    """Grand Feature Expansion, Phase 3 Feature 3: which coins are
    CONSISTENTLY profitable across every strategy that traded them --
    distinct from the plain aggregate ranking /coin-stats-style endpoints
    already give."""
    since_iso, _ = _period_bounds(period)
    return {"coins": coin_heatmap.compute_coin_heatmap(since_iso)}


@router.get("/api/paper-trading/coin-deep-dive/{symbol}")
def get_coin_deep_dive(symbol: str, period: str = "all"):
    """Grand Feature Expansion, Phase 3 Feature 17: pick one coin, see
    every strategy's own performance on it side by side."""
    since_iso, _ = _period_bounds(period)
    return coin_heatmap.compute_coin_deep_dive(symbol, since_iso)


@router.get("/api/paper-trading/alerts")
def get_alerts(limit: int = 30):
    return {"alerts": storage.list_paper_alerts(limit=limit)}


# ----------------------------------------- Custom Alert Rules (Grand Feature Expansion, Phase 4 Feature 25)

class CustomAlertRuleRequest(BaseModel):
    name: str
    metric: str
    comparison: str
    threshold: float
    strategy_id: Optional[str] = None


@router.get("/api/paper-trading/custom-alert-rules")
def list_custom_alert_rules_endpoint():
    return {"rules": custom_alerts.list_rules(), "metric_choices": custom_alerts.METRIC_CHOICES,
            "comparison_choices": custom_alerts.COMPARISON_CHOICES}


@router.post("/api/paper-trading/custom-alert-rules")
def create_custom_alert_rule_endpoint(req: CustomAlertRuleRequest):
    try:
        rule_id = custom_alerts.create_rule(
            req.name, req.metric, req.comparison, req.threshold, strategy_id=req.strategy_id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    sync.notify("custom_alert_rule", "created", f"Custom alert rule created: {req.name}")
    return {"ok": True, "rule_id": rule_id}


@router.post("/api/paper-trading/custom-alert-rules/{rule_id}/enabled")
def set_custom_alert_rule_enabled_endpoint(rule_id: str, enabled: bool = True):
    custom_alerts.set_rule_enabled(rule_id, enabled)
    return {"ok": True}


@router.delete("/api/paper-trading/custom-alert-rules/{rule_id}")
def delete_custom_alert_rule_endpoint(rule_id: str):
    custom_alerts.delete_rule(rule_id)
    sync.notify("custom_alert_rule", "deleted", f"Custom alert rule deleted: {rule_id}")
    return {"ok": True}


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


@router.get("/api/paper-trading/risk-pct-recommendations")
def get_risk_pct_recommendations():
    """Grand Feature Expansion, Phase 5 Feature 6: Optimal Risk % Per
    Strategy -- a suggestion only. Applying one reuses the existing,
    already-validated POST .../strategy-config/{id}/overrides endpoint;
    this endpoint never changes anything itself."""
    settings = pt_config.load()
    return {"recommendations": capital_allocation.compute_all_risk_pct_recommendations(
        settings.get("risk_pct_default", 1.0))}


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
    # Non-blocking: a 50-symbol ATR/MA pass can queue up behind other
    # concurrent DB work right after a restart (same reasoning as
    # /api/market, /api/data, and /api/home's disk_usage_bytes fixes).
    regimes = cache.cached_nonblocking(f"market_regime_{exchange}", 60, _compute, {})
    return {"exchange": exchange, "regimes": regimes}


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


@router.get("/api/paper-trading/strategy-correlation-matrix")
def get_strategy_correlation_matrix():
    """Grand Feature Expansion, Phase 3 Feature 4: strategy-vs-strategy
    correlation of DAILY REALIZED PnL (distinct from correlation-warnings
    above, which compares symbol price returns for open positions) --
    every strategy with at least one closed trade in the lookback window."""
    strategy_ids = [s["strategy_id"] for s in storage.list_paper_strategy_stats()]

    def _compute():
        return correlation.strategy_correlation_matrix(strategy_ids)
    return cache.cached("strategy_correlation_matrix", 300, _compute)


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


@router.get("/api/paper-trading/duplicate-exposure-warnings")
def get_duplicate_exposure_warnings():
    """Grand Feature Expansion, Phase 7 Feature 1: Duplicate Exposure
    Warning -- flags a coin currently traded by 2+ independent strategies
    at once, regardless of price correlation (see correlation-warnings
    above for the separate, price-correlation-based check)."""
    exchanges_cfg = base_config.load_or_seed("exchanges.json", base_config.DEFAULTS["exchanges.json"])
    exchange = exchanges_cfg["default"]
    return {"warnings": portfolio.detect_duplicate_exposure_warnings(exchange)}


@router.get("/api/paper-trading/strategy-exposure")
def get_strategy_exposure():
    """Grand Feature Expansion, Phase 3 Feature 5: Portfolio Heat Map --
    where open risk is concentrated BY STRATEGY (coin-exposure above
    already covers by-coin)."""
    exchanges_cfg = base_config.load_or_seed("exchanges.json", base_config.DEFAULTS["exchanges.json"])
    exchange = exchanges_cfg["default"]
    return {"exposure": portfolio.compute_strategy_exposure(exchange)}


@router.get("/api/paper-trading/direction-exposure")
def get_direction_exposure():
    """Grand Feature Expansion, Phase 3 Feature 5: Portfolio Heat Map --
    long vs short split across every strategy combined."""
    exchanges_cfg = base_config.load_or_seed("exchanges.json", base_config.DEFAULTS["exchanges.json"])
    exchange = exchanges_cfg["default"]
    return portfolio.compute_direction_exposure(exchange)


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
    silent_hours_enabled: Optional[bool] = None
    silent_hours_start_utc: Optional[str] = None
    silent_hours_end_utc: Optional[str] = None


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


class ChannelOverrideRequest(BaseModel):
    channel_id: Optional[str] = None  # None/empty removes the override


@router.post("/api/paper-trading/telegram/channel-override/{strategy_id}")
def set_telegram_channel_override(strategy_id: str, req: ChannelOverrideRequest):
    """Grand Feature Expansion, Phase 2 Feature 22: Multi-Channel Support.
    A dedicated endpoint (rather than folding this into the general
    /telegram/settings PATCH above) so the frontend only ever sends ONE
    strategy's change, never a full dict replace that could accidentally
    clobber every other strategy's routing."""
    overrides = telegram_bot.set_strategy_channel_override(strategy_id, req.channel_id)
    sync.notify("telegram", "channel_override_changed",
                f"{strategy_id} routed to {req.channel_id}" if req.channel_id else f"{strategy_id} reverted to the default channel")
    return {"ok": True, "strategy_channel_overrides": overrides}


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
def get_telegram_alert_status(lang: str = "ur"):
    """(Batch 2, Task 3) Whether 24+ hours have passed since the last
    Telegram signal (any tier) -- backs the dashboard's no-signal alert,
    shared by the Overview page and the Telegram Signals page."""
    return telegram_bot.no_signal_alert_status(lang=lang if lang == "en" else "ur")


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
        "best_strategy": telegram_analytics.best_performing_strategy(since_iso, until_iso),
    }


@router.get("/api/paper-trading/telegram/delivery-log")
def get_telegram_delivery_log(period: str = "all"):
    """EVERY signal the system generated in this period with its honest
    delivery status -- Sent / Withheld / Failed / Queued / Never sent.

    Deliberately different from /telegram/signals above, which only lists
    signals that were successfully SENT. While api.telegram.org is
    network-blocked, that endpoint can legitimately show zero rows on a day
    the system generated dozens of signals. This one always shows the full
    picture, and never reports a signal as sent unless a real successful
    send was recorded for it."""
    since_iso, until_iso = _period_bounds(period)
    signals = storage.list_generated_signals_with_delivery(since_iso, until_iso)
    rows = telegram_delivery.delivery_rows(signals)
    return {
        "period": period,
        "summary": telegram_delivery.delivery_summary(rows),
        "signals": rows,
    }


@router.get("/api/paper-trading/telegram/connection-status")
def get_telegram_connection_status():
    """Is Telegram delivery actually working right now, and if not, why.

    Deliberately makes NO network call: it reads the configuration plus
    what the real send attempts already recorded. A live probe on every
    page load would add a multi-second stall to a page whose whole point is
    to remain useful while the network is blocked. The Test Connection
    button (POST /telegram/test) is the deliberate live check."""
    settings = telegram_bot.public_settings()
    recent = storage.list_telegram_messages(limit=40)
    real = [m for m in recent if m["trigger_type"] in ("manual", "automatic", "daily_report")]
    last_success = next((m for m in real if m["success"]), None)
    last_failure = next((m for m in real if not m["success"]), None)

    if not settings["token_configured"] or not settings["channel_id"]:
        state, reason = "not_configured", "No bot token or channel ID has been saved yet."
    elif not settings["master_send_enabled"]:
        state, reason = "turned_off", "Sending is switched off, so nothing is being delivered on purpose."
    elif last_success and (not last_failure or last_success["sent_at"] > last_failure["sent_at"]):
        state = "working"
        # Name WHAT last got through. The most recent success is very often
        # a scheduled daily report rather than a trade signal, and "delivery
        # is working" sitting directly above "no signals sent in 4 weeks"
        # reads as a contradiction unless the difference is spelled out.
        # Both statements are true; this makes them legible together.
        kind = ("a scheduled daily report" if last_success["trigger_type"] == "daily_report"
                else "a trade signal")
        reason = (f"The connection itself is fine -- {kind} was delivered successfully on "
                  f"{last_success['sent_at'][:16].replace('T', ' ')}. That does not mean any trade "
                  f"signals have gone out recently; the signal log below is what says that.")
    elif last_failure:
        status_id = telegram_delivery.classify_attempt(last_failure)
        if status_id == "blocked_network":
            state = "blocked"
            reason = ("The request never reached Telegram -- the connection itself failed. "
                      "api.telegram.org is blocked at network level in this region. "
                      "A working proxy, or running this on a cloud server, resolves it.")
        else:
            state = "failing"
            reason = last_failure.get("error") or "Last send attempt failed."
    else:
        state, reason = "unknown", "No real send has been attempted yet, so there is nothing to judge from."

    return {
        "state": state,
        "reason": reason,
        "can_deliver": state == "working",
        "settings": settings,
        "last_success_at": (last_success or {}).get("sent_at"),
        "last_failure_at": (last_failure or {}).get("sent_at"),
        "last_failure_reason": (last_failure or {}).get("error"),
        "proxy_enabled": settings["proxy_enabled"],
        "proxy_configured": settings["proxy_configured"],
    }


@router.get("/api/paper-trading/telegram/preview/{position_id}")
def get_telegram_message_preview(position_id: str):
    """The exact message text that WOULD be sent for this signal, built by
    the same telegram_bot.format_signal_message() a real send uses -- so
    formatting can be verified now, long before delivery ever works.

    Builds the text only; it never sends and never writes to the message
    log. live_price is passed explicitly as None so this makes no live
    exchange call: a preview that stalls on a network fetch would defeat
    the purpose on a page built for a blocked network. The message
    therefore shows every field except the live "current price" line,
    which only a real send can fill in."""
    pos = storage.get_paper_position(position_id)
    if not pos:
        raise HTTPException(404, "signal not found")
    # Cached per signal: scoring confluence reads live market data, which
    # takes a couple of seconds on its own and considerably longer while
    # an engine tick is holding the storage lock -- long enough to blow
    # past the browser's request timeout, which is exactly how this first
    # showed up. A signal's message text barely changes minute to minute,
    # so a 5-minute TTL removes the stall on every reopen without making
    # the preview stale in any way that matters.
    return cache.cached(f"telegram_preview_{position_id}", 300, lambda: _build_telegram_preview(position_id, pos))


def _build_telegram_preview(position_id, pos):
    exchanges_cfg = base_config.load_or_seed("exchanges.json", base_config.DEFAULTS["exchanges.json"])
    try:
        conf = confluence.score_confluence(
            pos.get("strategy_id"), pos["symbol"], exchanges_cfg["default"],
            pos.get("market_state"), pos.get("session"), pos["direction"],
        )
    except Exception:
        conf = None
    try:
        reliability = telegram_bot._pattern_reliability_for(
            pos.get("strategy_id"), pos["symbol"], pos.get("market_state"), pos.get("session"),
        )
    except Exception:
        reliability = None
    explanation = signal_explainer.explain_signal(conf, reliability)
    grade = signal_explainer.grade_signal(conf, reliability)
    text = telegram_bot.format_signal_message(
        pos, conf, reliability, high_confidence=False, live_price=None,
        explanation_text=explanation, grade_result=grade,
    )
    # What the freshness gate would say about this signal RIGHT NOW, using
    # age only (the price-drift half needs a live price fetch, which this
    # endpoint deliberately avoids) -- so the preview can be honest about
    # whether this message would actually go out if sending worked.
    age_minutes = telegram_bot.signal_age_minutes(pos)
    stale = telegram_bot.is_signal_stale(pos)
    return {
        "position_id": position_id,
        "message_text": text,
        "quality_grade": grade.get("grade"),
        "grade_reason": grade.get("reason"),
        "symbol": pos.get("symbol"),
        "direction": pos.get("direction"),
        "strategy_name": pos.get("strategy_name"),
        "age_minutes": round(age_minutes, 1) if age_minutes is not None else None,
        "would_be_withheld_as_stale": bool(stale),
        "freshness_limit_minutes": telegram_bot.load_settings().get("signal_freshness_minutes"),
    }


@router.get("/api/paper-trading/signal-tracker/feed")
def get_live_signal_feed(limit: int = 50):
    """Batch 6, Task 5: Live Signal Tracker -- every real Telegram signal
    sent, newest first, with its real send-to-outcome status. Read-only;
    never sends, opens, or closes anything."""
    return signal_tracker.live_signal_feed(limit=limit)


@router.get("/api/paper-trading/signal-tracker/match-table")
def get_signal_match_table():
    """Batch 6, Task 5: per-strategy backtest vs paper vs Telegram-sent
    win rate, side by side, flagging real divergence once both sides have
    enough closed trades to trust. Read-only; never re-runs a backtest or
    changes anything about which strategies get signaled."""
    return signal_tracker.strategy_match_table()


class ChallengeRequest(BaseModel):
    start_amount: float
    target_amount: float
    days: int
    telegram_report_enabled: bool = False
    # Level 3 -- one-click start from a recommended path. Both or neither;
    # when both are given the challenge tracks that ONE real strategy-coin
    # combination's own trades instead of the system-wide blend. This is a
    # TRACKING scope choice only -- it can never alter risk_pct, position
    # sizing, or any trading behavior (see paper_trading.challenge_mode
    # and challenge_analysis module docstrings).
    scope_strategy_id: str | None = None
    scope_symbol: str | None = None


class ChallengeWhatIfRequest(BaseModel):
    start_amount: float
    target_amount: float
    days: int
    restrict_symbols: list[str] | None = None
    restrict_strategy_ids: list[str] | None = None


@router.get("/api/paper-trading/challenge")
def get_challenge():
    """Batch 9, Task 4: current Challenge Mode progress, or
    {"configured": False} if the CEO hasn't set one up. Read-only --
    tracking/reporting only, never touches risk_pct or any trading
    behavior."""
    progress = challenge_mode.compute_progress()
    if progress is None:
        return {"configured": False}
    return {"configured": True, **progress}


@router.post("/api/paper-trading/challenge")
def set_challenge(req: ChallengeRequest):
    """Every number here is chosen by the CEO themselves -- nothing
    hardcoded server-side. This endpoint is a TRACKING/ANALYSIS action
    only: it writes exclusively to challenge_settings.json and never
    touches paper_trading/config.json (risk_pct_default, position sizing,
    max_open_trades, etc.) or any other trading-behavior setting -- see
    paper_trading.challenge_mode.set_challenge()."""
    try:
        challenge_mode.set_challenge(
            req.start_amount, req.target_amount, req.days,
            telegram_report_enabled=req.telegram_report_enabled,
            scope_strategy_id=req.scope_strategy_id, scope_symbol=req.scope_symbol,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, **challenge_mode.compute_progress()}


@router.post("/api/paper-trading/challenge/clear")
def clear_challenge():
    challenge_mode.clear_challenge()
    return {"ok": True}


@router.get("/api/paper-trading/challenge/breakdown")
def get_challenge_breakdown():
    """Level 1: real per-strategy, per-coin, and per-strategy-coin
    performance breakdown -- read-only, computed entirely from stored
    closed trades."""
    from paper_trading import challenge_analysis
    return challenge_analysis.granular_breakdown()


@router.get("/api/paper-trading/challenge/best-portfolio")
def get_best_portfolio_suggestion(top_n: int = 3):
    """Grand Feature Expansion, Phase 5 Feature 11: Best Combination
    Auto-Suggest, extended to a multi-strategy PORTFOLIO -- top N distinct
    strategies' best coin each, by real PnL, filtered to statistically-
    trusted combinations. Purely informational -- applying an idea reuses
    each strategy's own existing enable/pause controls."""
    from paper_trading import challenge_analysis
    return challenge_analysis.suggest_best_portfolio(top_n=top_n)


@router.post("/api/paper-trading/challenge/recommend")
def post_challenge_recommend(req: ChallengeWhatIfRequest):
    """Level 2 (and the Level 3 What-If explorer, via the optional
    restrict_* filters): honest, confidence-graded, consistency-checked
    recommended paths toward a target -- always recomputed fresh from
    real historical data, never cached or extrapolated."""
    from paper_trading import challenge_analysis
    return challenge_analysis.recommend_paths(
        req.start_amount, req.target_amount, req.days,
        restrict_symbols=req.restrict_symbols, restrict_strategy_ids=req.restrict_strategy_ids,
    )


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


@router.get("/api/paper-trading/signal-detail/{position_id}")
def get_signal_detail(position_id: str):
    """Batch 10, Task 3: "Match Found" detail view for the Live Market
    Scan animation -- the same real confluence + Wilson-gate reliability
    data telegram_bot.send_signal_for_position already computes, and the
    same signal_explainer (Batch 7) that turns it into a plain Roman
    Urdu explanation and A+/A/B/C grade, plus the real Signal Freshness
    Gate check (Batch 5) -- but WITHOUT sending anything to Telegram.
    Read-only; works for any real position, sent or not."""
    pos = storage.get_paper_position(position_id)
    if not pos:
        raise HTTPException(404, "position not found")
    exchanges_cfg = base_config.load_or_seed("exchanges.json", base_config.DEFAULTS["exchanges.json"])
    exchange = exchanges_cfg["default"]
    try:
        conf = confluence.score_confluence(
            pos.get("strategy_id"), pos["symbol"], exchange,
            pos.get("market_state"), pos.get("session"), pos["direction"],
        )
    except Exception:
        conf = None
    try:
        reliability = telegram_bot._pattern_reliability_for(
            pos.get("strategy_id"), pos["symbol"], pos.get("market_state"), pos.get("session"),
        )
    except Exception:
        reliability = None
    fresh_ok, fresh_reason, live_price = telegram_bot.freshness_check(pos)
    return {
        "position": pos,
        "confluence": conf,
        "reliability": reliability,
        "explanation_text": signal_explainer.explain_signal(conf, reliability),
        "grade": signal_explainer.grade_signal(conf, reliability),
        "freshness": {"fresh": fresh_ok, "reason": fresh_reason, "live_price": live_price},
    }


@router.get("/api/paper-trading/graveyard")
def get_graveyard():
    return {"graveyard": storage.list_graveyard()}


class SimilarityCheck(BaseModel):
    concepts_used: list[str] = []


@router.post("/api/paper-trading/graveyard/check-similarity")
def check_graveyard_similarity(req: SimilarityCheck):
    return {"warnings": graveyard.check_similarity_warnings(req.concepts_used)}


@router.get("/api/paper-trading/retirement-suggestions")
def get_retirement_suggestions():
    """Grand Feature Expansion, Phase 4 Feature 4: Auto-Retirement
    Suggestion. Archiving itself reuses the existing, fully reversible
    POST /api/backtesting/strategies/{id}/archive -- this endpoint only
    ever surfaces the suggestion, never archives anything itself."""
    return {"suggestions": graveyard.compute_retirement_suggestions()}


@router.get("/api/paper-trading/trade-journal/export-pdf")
def export_trade_journal(strategy_id: Optional[str] = None, limit: int = 200):
    """Grand Feature Expansion, Phase 4 Feature 23: Trade Journal Export to
    PDF -- distinct from the only other paper-trading export (an Excel
    strategy-vs-strategy comparison, not a per-trade journal). Reuses
    reportlab exactly like the existing backtest PDF export -- no new
    dependency."""
    path = trade_journal_export.export_trade_journal_pdf(strategy_id=strategy_id, limit=limit)
    return FileResponse(path, filename=os.path.basename(path))


class CoinBlacklistRequest(BaseModel):
    symbol: str
    reason: Optional[str] = None


@router.get("/api/paper-trading/coin-blacklist")
def get_coin_blacklist():
    """Grand Feature Expansion, Phase 5 Feature 1: Coin Blacklist -- a
    genuine deny-list, distinct from coin_filter.py's shortlist() (a top-N
    allowlist/ranker, never an exclude mechanism)."""
    return {"blacklist": coin_blacklist.list_all()}


@router.post("/api/paper-trading/coin-blacklist")
def add_coin_blacklist(req: CoinBlacklistRequest):
    symbol = req.symbol.strip().upper()
    if not symbol:
        raise HTTPException(400, "symbol is required")
    coin_blacklist.add(symbol, req.reason)
    sync.notify("coin_blacklist", "added", f"Blacklisted {symbol}" + (f" ({req.reason})" if req.reason else ""))
    return {"ok": True}


@router.delete("/api/paper-trading/coin-blacklist/{symbol}")
def remove_coin_blacklist(symbol: str):
    coin_blacklist.remove(symbol)
    sync.notify("coin_blacklist", "removed", f"Removed {symbol.upper()} from the blacklist")
    return {"ok": True}


class PositionSizeCalculatorRequest(BaseModel):
    balance: float
    entry_price: float
    stop_loss: Optional[float] = None
    risk_pct: float = 1.0
    take_profit: Optional[float] = None
    leverage: float = 1.0


@router.post("/api/paper-trading/position-size-calculator")
def calculate_position_size(req: PositionSizeCalculatorRequest):
    """Grand Feature Expansion, Phase 5 Feature 13: Position Size
    Calculator -- pure calculation, never touches a real position or the
    trading engine."""
    if req.entry_price <= 0:
        raise HTTPException(400, "entry_price must be greater than 0")
    return position_size_calculator.calculate(
        req.balance, req.entry_price, req.stop_loss, req.risk_pct, req.take_profit, req.leverage)


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
