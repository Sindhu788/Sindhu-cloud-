"""Paper Trading settings -- same JSON-file-under-data/config pattern as
data_engine.config, so it's editable from the dashboard without a restart
and persists between runs. Defaults are deliberately conservative: dry_run
starts True so nothing executes automatically until the CEO explicitly
switches it on.
"""

from data_engine import config as base_config

_DEFAULTS = {
    "dry_run": True,
    "initial_balance": 10000.0,
    "risk_pct_default": 1.0,
    # Per STRATEGY, not a total shared across every strategy running --
    # each strategy independently caps out at this many distinct coins with
    # an open position at once (see paper_trading.risk_manager.evaluate).
    "max_open_trades": 5,
    "cooldown_minutes": 15,
    "priority_rule": "confidence",     # confidence | win_rate | profit | manual
    "opposite_signal_policy": "block", # block | allow | close_and_reverse
    "coin_filter_top_n": 20,
    "tick_interval_seconds": 60,
    "lookback_days": 20,
    "lesson_default_timeframe": "1h",
    "lesson_default_sl_pct": 2.0,
    "lesson_default_rr": 2.0,
    "daily_goal_pct": 2.0,
}


def load():
    return base_config.load_or_seed("paper_trading_settings.json", _DEFAULTS)


def save(settings):
    base_config.save_config("paper_trading_settings.json", settings)


def update(**fields):
    settings = load()
    settings.update({k: v for k, v in fields.items() if v is not None})
    save(settings)
    return settings
