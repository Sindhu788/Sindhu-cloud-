"""Configuration for SINDHU.

Defaults live here as plain Python constants. On first run they are written
out to JSON files under data/config/ so everything is user-editable without
touching code; on every subsequent run the JSON files win over these
defaults. This keeps config.py import-compatible with the rest of the
codebase (same constant names as before) while making settings persistent
and editable from the dashboard.
"""

import json
import os

from data_engine.paths import CONFIG_DIR, DATABASE_DIR, LOGS_DIR, DB_PATH, LOG_FILE, ensure_folders

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

# kept for backward compatibility with old imports
LOG_PATH = LOG_FILE

BINANCE_BASE_URL = "https://api.binance.com"

# --- hardcoded defaults (seed values for the JSON config files) ---

_DEFAULT_EXCHANGES = {
    # ccxt id -> display name. "binance" uses the existing lightweight REST
    # client; the others go through ccxt.
    "enabled": ["binance", "okx", "bybit", "bitget", "gate"],
    "default": "binance",
}

_DEFAULT_COINS = {
    "num_coins": 50,
    "quote_asset": "USDT",
}

_DEFAULT_TIMEFRAMES = {
    "base_interval": "1m",
    # 1m is fetched from the exchange and stored as source of truth; every
    # other timeframe is derived by resampling, so a candle never has to be
    # downloaded twice at different resolutions.
    "supported": [
        "1m", "3m", "5m", "15m", "30m",
        "1h", "2h", "4h", "6h", "12h",
        "1d", "1w",
    ],
}

_DEFAULT_APP_SETTINGS = {
    "history_days": 365,
    "request_delay_seconds": 0.25,
    "klines_limit": 1000,
    "max_retries": 5,
    "watch_interval_seconds": 300,
}


def load_or_seed(filename, defaults):
    """Read data/config/<filename>, creating it from `defaults` if missing.
    Used both at import time here and by the dashboard's Settings dialog to
    read/write live values without needing a process restart."""
    ensure_folders()
    path = os.path.join(CONFIG_DIR, filename)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(defaults, f, indent=2)
        return dict(defaults)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    merged = dict(defaults)
    merged.update(data)
    return merged


def save_config(filename, data):
    ensure_folders()
    path = os.path.join(CONFIG_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


_exchanges_cfg = load_or_seed("exchanges.json", _DEFAULT_EXCHANGES)
_coins_cfg = load_or_seed("coins.json", _DEFAULT_COINS)
_timeframes_cfg = load_or_seed("timeframes.json", _DEFAULT_TIMEFRAMES)
_app_cfg = load_or_seed("app_settings.json", _DEFAULT_APP_SETTINGS)

ENABLED_EXCHANGES = _exchanges_cfg["enabled"]
DEFAULT_EXCHANGE = _exchanges_cfg["default"]

NUM_COINS = _coins_cfg["num_coins"]
QUOTE_ASSET = _coins_cfg["quote_asset"]

BASE_INTERVAL = _timeframes_cfg["base_interval"]
SUPPORTED_INTERVALS = _timeframes_cfg["supported"]

HISTORY_DAYS = _app_cfg["history_days"]
REQUEST_DELAY_SECONDS = _app_cfg["request_delay_seconds"]
KLINES_LIMIT = _app_cfg["klines_limit"]
MAX_RETRIES = _app_cfg["max_retries"]
WATCH_INTERVAL_SECONDS = _app_cfg["watch_interval_seconds"]

DEFAULTS = {
    "exchanges.json": _DEFAULT_EXCHANGES,
    "coins.json": _DEFAULT_COINS,
    "timeframes.json": _DEFAULT_TIMEFRAMES,
    "app_settings.json": _DEFAULT_APP_SETTINGS,
}

# pandas resample rule for each interval (used to derive from 1m)
RESAMPLE_RULE = {
    "1m": "1min", "3m": "3min", "5m": "5min", "15m": "15min", "30m": "30min",
    "1h": "1h", "2h": "2h", "4h": "4h", "6h": "6h", "8h": "8h", "12h": "12h",
    "1d": "1D", "3d": "3D", "1w": "1W-MON", "1M": "MS",
}
