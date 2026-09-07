from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from data_engine import config, db_backend
from data_engine.paths import DATABASE_DIR
from data_engine.exchanges.registry import ALL_EXCHANGE_IDS
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
    exchanges_cfg = config.load_or_seed("exchanges.json", config.DEFAULTS["exchanges.json"])
    coins_cfg = config.load_or_seed("coins.json", config.DEFAULTS["coins.json"])
    app_cfg = config.load_or_seed("app_settings.json", config.DEFAULTS["app_settings.json"])
    web_cfg = config.load_or_seed("web_settings.json", _DEFAULT_WEB_SETTINGS)

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
        cfg = config.load_or_seed("exchanges.json", config.DEFAULTS["exchanges.json"])
        cfg["default"] = req.exchange
        config.save_config("exchanges.json", cfg)

    if req.quote_asset is not None or req.num_coins is not None:
        cfg = config.load_or_seed("coins.json", config.DEFAULTS["coins.json"])
        if req.quote_asset is not None:
            cfg["quote_asset"] = req.quote_asset.upper()
        if req.num_coins is not None:
            cfg["num_coins"] = req.num_coins
        config.save_config("coins.json", cfg)

    if req.theme is not None or req.refresh_speed_seconds is not None:
        cfg = config.load_or_seed("web_settings.json", _DEFAULT_WEB_SETTINGS)
        if req.theme is not None:
            cfg["theme"] = req.theme
        if req.refresh_speed_seconds is not None:
            cfg["refresh_speed_seconds"] = req.refresh_speed_seconds
        config.save_config("web_settings.json", cfg)

    if req.default_risk_pct is not None:
        cfg = config.load_or_seed("app_settings.json", config.DEFAULTS["app_settings.json"])
        cfg["default_risk_pct"] = req.default_risk_pct
        config.save_config("app_settings.json", cfg)

    sync.notify("settings", "updated", "Settings changed")
    return {"ok": True}
