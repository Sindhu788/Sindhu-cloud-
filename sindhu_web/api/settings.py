from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from data_engine import config, db_backend
from data_engine.paths import DATABASE_DIR
from data_engine.exchanges.registry import ALL_EXCHANGE_IDS
from paper_trading import cost_tracker, coin_event_caution
from sindhu_web import sync

router = APIRouter()

_DEFAULT_WEB_SETTINGS = {"theme": "dark", "refresh_speed_seconds": 10}
POSTGRES_FREE_TIER_DAYS = 30


def _postgres_expiry_notice(app_cfg):
    """Master 15-Item task, Item 12: only meaningful when actually running
    against Postgres (db_backend.IS_POSTGRES) -- a local SQLite install
    has no such expiry at all, so this stays None there rather than
    showing a scary countdown that doesn't apply."""
    if not db_backend.IS_POSTGRES:
        return None
    created = datetime.strptime(app_cfg["postgres_free_tier_created_date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    expiry = created + timedelta(days=POSTGRES_FREE_TIER_DAYS)
    days_remaining = (expiry - datetime.now(timezone.utc)).days
    return {
        "created_date": app_cfg["postgres_free_tier_created_date"],
        "expiry_date": expiry.strftime("%Y-%m-%d"),
        "days_remaining": days_remaining,
    }


@router.get("/api/settings")
def get_settings():
    # Master Task Grand Batch, Phase 2.2 bug fix: load_persistent instead of
    # load_or_seed -- on the cloud deployment these plain JSON files were
    # wiped on every restart/redeploy/sleep-wake, silently reverting
    # Exchange/Coins/Theme/Refresh Speed/Default Risk % to hardcoded
    # defaults even though the dashboard's save appeared to succeed.
    exchanges_cfg = config.load_persistent("settings_exchanges", "exchanges.json", config.DEFAULTS["exchanges.json"])
    coins_cfg = config.load_persistent("settings_coins", "coins.json", config.DEFAULTS["coins.json"])
    app_cfg = config.load_persistent("settings_app", "app_settings.json", config.DEFAULTS["app_settings.json"])
    web_cfg = config.load_persistent("settings_web", "web_settings.json", _DEFAULT_WEB_SETTINGS)

    return {
        "exchange": exchanges_cfg["default"],
        "available_exchanges": ALL_EXCHANGE_IDS,
        "quote_asset": coins_cfg["quote_asset"],
        "num_coins": coins_cfg["num_coins"],
        "history_days": app_cfg["history_days"],
        "default_risk_pct": app_cfg.get("default_risk_pct", 1.0),
        "theme": web_cfg["theme"],
        "refresh_speed_seconds": web_cfg["refresh_speed_seconds"],
        # Read-only: relocating the live 3GB database is a data-safety risk,
        # not something to trigger from a settings toggle. Shown for
        # visibility only.
        "database_location": DATABASE_DIR,
        "postgres_free_tier": _postgres_expiry_notice(app_cfg),
    }


class SettingsUpdate(BaseModel):
    exchange: Optional[str] = None
    quote_asset: Optional[str] = None
    num_coins: Optional[int] = None
    theme: Optional[str] = None
    refresh_speed_seconds: Optional[int] = None
    default_risk_pct: Optional[float] = None


@router.post("/api/settings")
def update_settings(req: SettingsUpdate):
    if req.exchange is not None:
        cfg = config.load_persistent("settings_exchanges", "exchanges.json", config.DEFAULTS["exchanges.json"])
        cfg["default"] = req.exchange
        config.save_persistent("settings_exchanges", "exchanges.json", cfg)

    if req.quote_asset is not None or req.num_coins is not None:
        cfg = config.load_persistent("settings_coins", "coins.json", config.DEFAULTS["coins.json"])
        if req.quote_asset is not None:
            cfg["quote_asset"] = req.quote_asset.upper()
        if req.num_coins is not None:
            cfg["num_coins"] = req.num_coins
        config.save_persistent("settings_coins", "coins.json", cfg)

    if req.theme is not None or req.refresh_speed_seconds is not None:
        cfg = config.load_persistent("settings_web", "web_settings.json", _DEFAULT_WEB_SETTINGS)
        if req.theme is not None:
            cfg["theme"] = req.theme
        if req.refresh_speed_seconds is not None:
            cfg["refresh_speed_seconds"] = req.refresh_speed_seconds
        config.save_persistent("settings_web", "web_settings.json", cfg)

    if req.default_risk_pct is not None:
        cfg = config.load_persistent("settings_app", "app_settings.json", config.DEFAULTS["app_settings.json"])
        cfg["default_risk_pct"] = req.default_risk_pct
        config.save_persistent("settings_app", "app_settings.json", cfg)

    sync.notify("settings", "updated", "Settings changed")
    return {"ok": True}


# --------------------------------------------------------------- Grand Master Batch, Phase 4 Item 6: cost tracker

class CostItemCreate(BaseModel):
    label: str
    amount_usd: float
    period: str = "monthly"
    note: Optional[str] = None


@router.get("/api/settings/costs")
def get_cost_tracker():
    return cost_tracker.summary()


@router.post("/api/settings/costs")
def add_cost_tracker_item(req: CostItemCreate):
    item = cost_tracker.add_cost(req.label, req.amount_usd, req.period, req.note)
    return {"ok": True, "item": item}


@router.delete("/api/settings/costs/{cost_id}")
def delete_cost_tracker_item(cost_id: str):
    removed = cost_tracker.remove_cost(cost_id)
    return {"ok": removed}


# --------------------------------------------------------------- Grand Master Batch, Phase 4 Item 12: coin event caution

class CoinEventCautionSettingsUpdate(BaseModel):
    cryptopanic_api_key: Optional[str] = None


@router.get("/api/settings/coin-event-caution")
def get_coin_event_caution_settings():
    settings = coin_event_caution.load_settings()
    return {"api_key_configured": bool(settings.get("cryptopanic_api_key"))}


@router.post("/api/settings/coin-event-caution")
def save_coin_event_caution_settings(req: CoinEventCautionSettingsUpdate):
    coin_event_caution.save_settings(cryptopanic_api_key=req.cryptopanic_api_key)
    return {"ok": True}


@router.get("/api/settings/coin-event-caution/{symbol}")
def check_coin_event_caution(symbol: str):
    return coin_event_caution.check_coin_caution(symbol)
