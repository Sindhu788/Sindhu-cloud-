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
    # Grand Feature Expansion, Phase 1 Feature 5: Account-wide Drawdown
    # Circuit-Breaker. Unlike the per-strategy threshold above (one
    # strategy's own peak, pauses only that strategy), this compares the
    # COMBINED balance across every book against its own all-time peak and
    # halts ALL new entries system-wide once crossed -- deliberately a
    # stricter/larger bar than any single strategy's own threshold, since
    # tripping it is a bigger action. Existing open positions are still
    # monitored and closed normally; only new entries are blocked, and only
    # a fresh kill switch activation ever force-closes anything.
    "account_drawdown_pause_pct_threshold": 20.0,
    # Grand Feature Expansion, Phase 5 Feature 2: Time-of-Day Trading
    # Filter -- blocks NEW entries during a configured UTC hour window
    # (e.g. known-illiquid overnight hours), same overnight-wraparound
    # window convention as Telegram's Silent Hours DND (Phase 2 Feature
    # 24), but gates real trade execution instead of muting a
    # notification sound. Off by default -- start/end equal means "always
    # off" here too. Existing open positions are never affected, only new
    # entries; same scope as every other pre-entry risk gate.
    "time_filter_enabled": False,
    "time_filter_block_start_utc": "00:00",
    "time_filter_block_end_utc": "00:00",
    # Grand Feature Expansion, Phase 5 Feature 9: Profit-Lock Trailing
    # Stop -- once a position has moved in its favor by at least
    # profit_lock_trigger_r times its own original risk (entry-to-stop
    # distance), the stop-loss trails behind the position's best price
    # seen so far (Phase 3's MAE/MFE excursion tracking, reused as-is) to
    # lock in profit_lock_trail_pct of that favorable move -- e.g. the
    # defaults (trigger 1.0R, trail 50%) mean: once up 1R, guarantee at
    # least 0.5R either way it goes from there. Off by default -- a
    # brand-new execution-affecting mechanism. The stop-loss is only ever
    # tightened, never loosened, regardless of these settings.
    "profit_lock_enabled": False,
    "profit_lock_trigger_r": 1.0,
    "profit_lock_trail_pct": 50.0,
    # Grand Feature Expansion, Phase 5 Feature 10: Ensemble Voting
    # Confirmation -- how many INDEPENDENT strategies/lessons must agree
    # on the same symbol+direction within the same tick before any of them
    # can open (only checked when feature_toggles.ensemble_voting_enabled
    # is on). 2 is the smallest number that is actually "agreement"
    # between more than one source.
    "ensemble_voting_min_agreeing_strategies": 2,
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
