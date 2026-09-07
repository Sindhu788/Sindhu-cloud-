"""Master 15-Item task, Item 13: Evolution Scope Control. Same JSON-file-
under-data/config pattern as paper_trading/config.py (dashboard-editable,
restart-persistent, Postgres-aware via cloud_settings when DATABASE_URL is
set) -- the Evolution Engine had no settings file at all before this;
every limit used to be a hardcoded module constant in governor.py.

Three modes, since this is a solo, part-time project and unlimited
generations on every strategy forever was never really the intent:
  - conservative (DEFAULT): only strategies clearing a minimum real bar
    (Profit Factor >= 0.7 OR >= 25 completed backtest trades) get
    automatic generations at all, capped at 3 generations per lineage.
  - balanced: no minimum bar, but only the top 25 lineages by their own
    evolution_score get automatic generations, capped at 5 per lineage.
  - aggressive: today's original, unrestricted behavior -- every lineage
    with real trades is eligible, capped at governor.MAX_GENERATIONS_
    PER_STRATEGY (25), no "matured" concept applied at all. NOT the
    default -- an explicit CEO opt-in back to the old behavior.

None of this touches PAPER TRADING's own safety gates (Wilson score,
Confluence, Signal Freshness, 5-coin cap, Drawdown Protection) -- this is
purely about how many BACKTEST-ONLY generations the Evolution Engine
is allowed to spend CPU generating for itself, never live trading."""
from datetime import datetime, timezone

from data_engine import config as base_config, db_backend, storage
from evolution_engine.governor import MAX_GENERATIONS_PER_STRATEGY

_SETTINGS_KEY = "evolution_settings"

_DEFAULTS = {
    "evolution_mode": "conservative",  # conservative | balanced | aggressive
}

MODE_PARAMS = {
    "conservative": {"min_profit_factor": 0.7, "min_trades": 25, "max_generations": 3, "top_n": None},
    "balanced": {"min_profit_factor": None, "min_trades": None, "max_generations": 5, "top_n": 25},
    "aggressive": {"min_profit_factor": None, "min_trades": None, "max_generations": MAX_GENERATIONS_PER_STRATEGY, "top_n": None},
}


def load():
    if db_backend.IS_POSTGRES:
        saved = storage.get_cloud_setting(_SETTINGS_KEY)
        merged = dict(_DEFAULTS)
        if saved:
            merged.update(saved)
        return merged
    return base_config.load_or_seed("evolution_settings.json", _DEFAULTS)


def save(settings):
    if db_backend.IS_POSTGRES:
        storage.save_cloud_setting(_SETTINGS_KEY, settings, datetime.now(timezone.utc).isoformat())
        return
    base_config.save_config("evolution_settings.json", settings)


def update(**fields):
    settings = load()
    settings.update({k: v for k, v in fields.items() if v is not None})
    save(settings)
    return settings


def current_mode_params():
    """Returns (mode: str, params: dict) -- params always has
    min_profit_factor/min_trades/max_generations/top_n keys, None for
    whichever don't apply to that mode. Falls back to conservative for an
    unrecognized/corrupted saved value rather than silently defaulting to
    unrestricted behavior."""
    mode = load().get("evolution_mode", "conservative")
    if mode not in MODE_PARAMS:
        mode = "conservative"
    return mode, MODE_PARAMS[mode]
