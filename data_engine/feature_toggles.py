"""Centralized on/off state for SINDHU's automated background features
(the dashboard's Feature Control Center) -- a visibility/control layer
only. Each flag is read at the exact call site the feature already ran
from; turning a flag off just skips that specific future call, it never
touches an already-open position, already-written history, or the
Paper Trading engine's own start/stop state.

Follows the exact same load_or_seed/save_config JSON-file pattern already
used by ai_trade_review_settings.json, telegram_settings.json and
backup_settings.json (see data_engine.config).
"""

from data_engine import config

_FILE = "feature_toggles.json"

DEFAULTS = {
    "master_pause_all": False,
    "auto_avoid_enabled": True,
    "lesson_auto_apply_enabled": True,
    "drawdown_protection_enabled": True,
    "dynamic_risk_sizing_enabled": True,
    "capital_allocation_enabled": True,
    "backup_enabled": True,
    "weekly_report_enabled": True,
    "sindhu_strategy_autogen_enabled": True,
}


def get_toggles():
    return config.load_or_seed(_FILE, DEFAULTS)


def set_toggle(key, value):
    if key not in DEFAULTS:
        raise ValueError(f"unknown feature toggle: {key}")
    data = get_toggles()
    data[key] = bool(value)
    config.save_config(_FILE, data)
    return data


def set_master_pause(value):
    return set_toggle("master_pause_all", value)


def is_master_paused():
    return bool(get_toggles().get("master_pause_all", False))


def is_enabled(key):
    """True only if the master pause is off AND this specific feature's
    own flag is on. `key` must be one of DEFAULTS' keys."""
    data = get_toggles()
    if data.get("master_pause_all"):
        return False
    return bool(data.get(key, True))
