"""Paper Trading settings -- same JSON-file-under-data/config pattern as
data_engine.config, so it's editable from the dashboard without a restart
and persists between runs. Defaults are deliberately conservative: dry_run
starts True so nothing executes automatically until the CEO explicitly
switches it on.

Cloud persistence: on a host with DATABASE_URL set (Postgres), these
settings are stored in the cloud_settings table instead of the local file
-- the local file lives on Render's ephemeral filesystem, which is wiped
on every restart/redeploy/sleep-wake, silently reverting a CEO's real
choice (e.g. turning Dry Run Mode off) back to the conservative default.
See data_engine/db_backend.py's cloud_settings comment and
sindhu_web/auth.py for the identical pattern used for login credentials.
Local laptop behavior (DATABASE_URL unset) is completely unchanged.
"""

from datetime import datetime, timezone

from data_engine import config as base_config, db_backend, storage

_SETTINGS_KEY = "paper_trading_settings"

_DEFAULTS = {
    "dry_run": True,
    # Batch 9, Task 3: the CEO's last EXPLICIT start/stop choice for the
    # Paper Trading Engine, persisted so a server restart (including an
    # ungraceful one -- power loss, crash) restores the engine to
    # whatever it actually was, never silently defaulting to off just
    # because the in-memory PaperTradingEngine._running flag always
    # starts False on a fresh process. Written the instant start/stop is
    # called (see sindhu_web/api/paper_trading.py), same as every other
    # setting in this file -- never only on a clean shutdown.
    "engine_enabled": False,
    "initial_balance": 10000.0,
    "risk_pct_default": 1.0,
    # Per STRATEGY, not a total shared across every strategy running --
    # each strategy independently caps out at this many distinct coins with
    # an open position at once (see paper_trading.risk_manager.evaluate).
    "max_open_trades": 5,
    "cooldown_minutes": 15,
    "priority_rule": "confidence",     # confidence | win_rate | profit | manual
    "opposite_signal_policy": "block", # block | allow | close_and_reverse
    # The full 50-coin universe (matches data_engine.config's own
    # num_coins default, and the CEO's real already-saved local setting)
    # -- NOT a smaller default that only matters on a FRESH install with
    # no paper_trading_settings.json yet (a brand-new local install, or
    # the lightweight cloud runner, which starts with no local settings
    # file and no access to the CEO's real one). An existing installation
    # already has its own saved value in that file and is completely
    # unaffected by this default either way (data_engine.config.
    # load_or_seed only ever applies a default once, before the file
    # exists).
    "coin_filter_top_n": 50,
    "tick_interval_seconds": 60,
    "lookback_days": 20,
    "lesson_default_timeframe": "1h",
    "lesson_default_sl_pct": 2.0,
    "lesson_default_rr": 2.0,
    "daily_goal_pct": 2.0,
    # Drawdown Protection Engine (Risk & Safety Group, item 4): a strategy
    # pauses NEW entries (existing open positions still managed normally)
    # once either bar is crossed. The loss-streak bar is set higher than
    # auto_avoid's per-PATTERN threshold (5) since this pauses the WHOLE
    # strategy across every coin/condition, a bigger action that deserves a
    # stricter bar. 15% drawdown-from-peak is a common, conservative risk
    # management convention (comparable to typical prop-firm daily/overall
    # drawdown limits) -- not a custom invention.
    "drawdown_pause_streak_threshold": 7,
    "drawdown_pause_pct_threshold": 15.0,
}


def load():
    if db_backend.IS_POSTGRES:
        saved = storage.get_cloud_setting(_SETTINGS_KEY)
        merged = dict(_DEFAULTS)
        if saved:
            merged.update(saved)
        return merged
    return base_config.load_or_seed("paper_trading_settings.json", _DEFAULTS)


def save(settings):
    if db_backend.IS_POSTGRES:
        storage.save_cloud_setting(_SETTINGS_KEY, settings, datetime.now(timezone.utc).isoformat())
        return
    base_config.save_config("paper_trading_settings.json", settings)


def update(**fields):
    settings = load()
    settings.update({k: v for k, v in fields.items() if v is not None})
    save(settings)
    return settings
