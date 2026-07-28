"""Feature Control Center (Dashboard Control & Visibility, Part 2): a
single place to see and toggle every automated background feature. This
is a visibility/control layer ONLY -- every toggle here just gates a call
site that already existed (see data_engine.feature_toggles and the
per-feature modules it's read from); nothing about the underlying
calculation, the backtest engine, or trade execution is touched.

Two kinds of feature live here:
  - Toggles backed by the new unified data/config/feature_toggles.json
    (auto_avoid, lesson_auto_apply, drawdown_protection, dynamic_risk,
    capital_allocation, backup, weekly_report, sindhu_strategy_autogen).
  - Toggles that already had their OWN settings file before this Control
    Center existed (AI Trade Review, Telegram auto-send) -- reused as-is
    rather than duplicated, so there is only ever one source of truth for
    each flag.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from data_engine import storage, feature_toggles
from paper_trading import ai_trade_review, telegram_bot

router = APIRouter()


def _ago(iso_ts):
    if not iso_ts:
        return None
    try:
        dt = datetime.fromisoformat(iso_ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        seconds = (datetime.now(timezone.utc) - dt).total_seconds()
    except Exception:
        return None
    if seconds < 90:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)} minute(s) ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)} hour(s) ago"
    return f"{int(seconds // 86400)} day(s) ago"


def _drawdown_status(enabled):
    paused = storage.list_paused_strategies()
    if not paused:
        return "no strategy currently paused"
    most_recent = max(paused, key=lambda p: p["paused_at"] or "")
    return f'{len(paused)} strategy(ies) paused -- most recently "{most_recent["strategy_id"]}" {_ago(most_recent["paused_at"]) or ""}'.strip()


def _auto_avoid_status(enabled):
    rules = storage.list_paper_auto_avoid_rules(active_only=True)
    if not rules:
        return "no active avoid rules"
    return f"{len(rules)} active avoid rule(s)"


def _capital_allocation_status(enabled):
    allocations = storage.list_capital_allocations()
    non_default = [a for a in allocations if a["capital_multiplier"] not in (None, 1.0)]
    if not enabled:
        return f"frozen -- {len(non_default)} strategy(ies) keep their last multiplier until re-enabled"
    return f"{len(non_default)} strategy(ies) currently have an adjusted multiplier"


def _static_status(text):
    return lambda enabled: text


def _ai_trade_review_status(enabled):
    return "writes one AI sentence per closed trade" if enabled else "off (uses no AI tokens)"


def _telegram_status(enabled):
    return "sending trade signals + results automatically" if enabled else "off (manual send only)"


# id -> (name, description, category, get_enabled, set_enabled, status_fn, extra)
def _feature_defs():
    toggles = feature_toggles.get_toggles()
    telegram_settings = telegram_bot.load_settings()
    return [
        {
            "id": "auto_avoid_enabled", "name": "Pattern Auto-Avoid",
            "description": "Automatically pauses a specific losing pattern (same strategy + coin + condition) after 5 losses in a row.",
            "category": "Risk & Safety",
            "enabled": toggles["auto_avoid_enabled"],
            "status": _auto_avoid_status(toggles["auto_avoid_enabled"]),
        },
        {
            "id": "drawdown_protection_enabled", "name": "Drawdown Protection",
            "description": "Automatically pauses a strategy after 7 losses in a row or a 15% drawdown from its peak.",
            "category": "Risk & Safety",
            "enabled": toggles["drawdown_protection_enabled"],
            "status": _drawdown_status(toggles["drawdown_protection_enabled"]),
        },
        {
            "id": "dynamic_risk_sizing_enabled", "name": "Dynamic Risk Sizing",
            "description": "Automatically cuts risk in half on trades entered during high-volatility market conditions.",
            "category": "Risk & Safety",
            "enabled": toggles["dynamic_risk_sizing_enabled"],
            "status": "active" if toggles["dynamic_risk_sizing_enabled"] else "off -- always uses the plain configured risk %",
        },
        {
            "id": "lesson_auto_apply_enabled", "name": "Lesson Auto-Apply",
            "description": "Automatically promotes a strongly one-sided trading pattern into a live confidence boost or penalty.",
            "category": "Self-Learning",
            "enabled": toggles["lesson_auto_apply_enabled"],
            "status": "re-scanning every tick" if toggles["lesson_auto_apply_enabled"] else "off -- confidence scoring ignores new patterns",
        },
        {
            "id": "capital_allocation_enabled", "name": "Capital Allocation",
            "description": "Automatically gives more (or less) virtual capital to a strategy based on its own track record (Sharpe Ratio).",
            "category": "Self-Learning",
            "enabled": toggles["capital_allocation_enabled"],
            "status": _capital_allocation_status(toggles["capital_allocation_enabled"]),
        },
        {
            "id": "sindhu_strategy_autogen_enabled", "name": "Daily Strategy Generator",
            "description": "Automatically generates up to 11 new candidate trading strategies every day.",
            "category": "Self-Learning",
            "enabled": toggles["sindhu_strategy_autogen_enabled"],
            "status": "runs on its own daily schedule" if toggles["sindhu_strategy_autogen_enabled"] else "off -- no new candidates will be generated",
        },
        {
            "id": "ai_trade_review_enabled", "name": "AI Trade Review",
            "description": "Automatically writes a one-sentence plain-English explanation for each closed trade using AI.",
            "category": "Self-Learning",
            "enabled": ai_trade_review.is_enabled(),
            "status": _ai_trade_review_status(ai_trade_review.is_enabled()),
        },
        {
            "id": "telegram_auto_send_enabled", "name": "Telegram Auto-Send",
            "description": "Automatically posts high-confidence trade signals and results to a Telegram channel.",
            "category": "Signals",
            "enabled": telegram_settings.get("auto_send_enabled", False),
            "status": _telegram_status(telegram_settings.get("auto_send_enabled", False)),
            "auto_manual": True,
        },
        {
            "id": "backup_enabled", "name": "Automated Backup",
            "description": "Automatically backs up the database every few hours.",
            "category": "Other",
            "enabled": toggles["backup_enabled"],
            "status": "scheduled" if toggles["backup_enabled"] else "off -- no automatic backups until re-enabled",
        },
        {
            "id": "weekly_report_enabled", "name": "Weekly Auto-Report",
            "description": "Automatically writes a plain-language performance summary every 7 days.",
            "category": "Other",
            "enabled": toggles["weekly_report_enabled"],
            "status": "scheduled" if toggles["weekly_report_enabled"] else "off -- no new weekly reports until re-enabled",
        },
    ]


@router.get("/api/feature-control/state")
def get_state():
    return {
        "master_pause_all": feature_toggles.is_master_paused(),
        "features": _feature_defs(),
    }


class ToggleRequest(BaseModel):
    feature_id: str
    enabled: bool


_UNIFIED_KEYS = {
    "auto_avoid_enabled", "lesson_auto_apply_enabled", "drawdown_protection_enabled",
    "dynamic_risk_sizing_enabled", "capital_allocation_enabled", "backup_enabled",
    "weekly_report_enabled", "sindhu_strategy_autogen_enabled",
}


@router.post("/api/feature-control/toggle")
def toggle_feature(req: ToggleRequest):
    if req.feature_id in _UNIFIED_KEYS:
        feature_toggles.set_toggle(req.feature_id, req.enabled)
    elif req.feature_id == "ai_trade_review_enabled":
        ai_trade_review.set_enabled(req.enabled)
    elif req.feature_id == "telegram_auto_send_enabled":
        telegram_bot.save_settings(auto_send_enabled=req.enabled)
    else:
        raise HTTPException(404, f"unknown feature_id: {req.feature_id}")
    return {"ok": True, "feature_id": req.feature_id, "enabled": req.enabled}


class MasterPauseRequest(BaseModel):
    enabled: bool


@router.post("/api/feature-control/master-pause")
def set_master_pause(req: MasterPauseRequest):
    """Pauses (or resumes) every automated ACTION at once -- Paper Trading
    itself keeps running (still opens/closes/monitors trades on its own
    configured rules), only the extra automation layered on top is
    silenced. Nothing already written (paused strategies, avoid rules,
    lessons, allocations) is deleted or reset; they simply stop being
    re-evaluated/acted on until unpaused."""
    feature_toggles.set_master_pause(req.enabled)
    return {"ok": True, "master_pause_all": req.enabled}
