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
    # Phase 8 verification, Finding 3: real exchange commission (0.1% =
    # Binance spot's standard taker fee), deducted at close on top of the
    # already-modeled slippage+spread -- see
    # position_manager._DEFAULT_COMMISSION_PCT's own comment for the exact
    # formula (matches backtest_engine.engine's existing commission_pct
    # computation). Set to 0 to simulate a fee-free/maker-rebate account.
    "commission_pct": 0.001,
    # Per STRATEGY, not a total shared across every strategy running --
    # each strategy independently caps out at this many distinct coins with
    # an open position at once (see paper_trading.risk_manager.evaluate).
    "max_open_trades": 5,
    # Grand Master Batch #2, Phase 3.3: Portfolio-Level Exposure Control.
    # paper_trading.portfolio.compute_coin_exposure() already computed this
    # number for the dashboard's own warnings but never enforced it (see
    # that module's own "purely informational... never blocks a trade"
    # boundary) -- risk_manager.evaluate() now rejects a NEW entry once a
    # single coin's combined risk across EVERY strategy would exceed this
    # % of initial_balance. 10% is a deliberately generous default (this
    # is a brand-new enforced cap, not something any existing strategy mix
    # was ever tuned against) -- it only bites when several strategies
    # genuinely pile risk onto the same coin at once, not ordinary single-
    # strategy trading. Set to 0 to disable.
    "max_portfolio_risk_pct_per_coin": 10.0,
    "cooldown_minutes": 15,
    # Master Task Grand Batch, Phase 2.1: default changed from "confidence"
    # to "confidence_and_win_rate" -- ranking by confidence alone ignored
    # each strategy's real track record entirely. "win_rate"/"profit"/
    # "manual" remain selectable for a CEO who wants pure single-factor
    # ranking (win_rate and profit are now real -- see guards.rank_candidates
    # and engine.py's per-candidate population right before ranking; "manual"
    # has no data source yet -- see guards.py's rank_candidates docstring).
    "priority_rule": "confidence_and_win_rate",  # confidence | win_rate | profit | manual | confidence_and_win_rate
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
    # 2026-09-16 audit (CEO Section 10.1): per-strategy cooling-off -- after
    # this many CONSECUTIVE losses a strategy opens nothing new for
    # cooling_off_hours (from its latest losing close), then resumes on its
    # own. Shorter than the manual-resume pause above; only ever adds a
    # reason not to trade. 0 = off. See paper_trading/cooling_off.py.
    "cooling_off_loss_streak": 4,
    "cooling_off_hours": 3.0,
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
    # Master 15-Item task, Item 8: Mobile Push Notifications -- ntfy.sh
    # topic name (see paper_trading/push_notifications.py's own docstring
    # for why ntfy.sh over browser Web Push). Empty until the CEO picks a
    # topic name (their own arbitrary secret string, e.g. via the ntfy
    # app) -- no account/signup needed on either side, but a topic name IS
    # effectively a shared secret (anyone who knows it can subscribe), so
    # this is never auto-generated/guessed on the CEO's behalf.
    "ntfy_topic": "",
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


# --------------------------------------------------------------- 2026-09-16 audit: settings save UX
#
# Validation, defaults and a change history for the dashboard's Settings
# save. Validation only rejects values that are nonsensical for the field
# itself (negative balance, a risk % above 100, an unknown enum) -- it never
# narrows or widens any safety gate's own threshold.

_PRIORITY_RULES = {"confidence_and_win_rate", "confidence", "win_rate", "profit", "manual"}
_OPPOSITE_POLICIES = {"block", "allow", "close_and_reverse"}

# field -> (kind, min, max, min_inclusive); None bound = unbounded
_NUMERIC_RULES = {
    "initial_balance": ("float", 0, None, False),
    "risk_pct_default": ("float", 0, 100, False),
    "max_open_trades": ("int", 1, None, True),
    "cooldown_minutes": ("int", 0, None, True),
    "coin_filter_top_n": ("int", 1, None, True),
    "tick_interval_seconds": ("int", 1, None, True),
    "lookback_days": ("int", 1, None, True),
    "lesson_default_sl_pct": ("float", 0, 100, False),
    "lesson_default_rr": ("float", 0, None, False),
    "daily_goal_pct": ("float", 0, None, True),
    "profit_lock_trigger_r": ("float", 0, None, False),
    "profit_lock_trail_pct": ("float", 0, 100, True),
    "ensemble_voting_min_agreeing_strategies": ("int", 1, None, True),
    "cooling_off_loss_streak": ("int", 0, None, True),
    "cooling_off_hours": ("float", 0, 168, True),
}


def _valid_hhmm(value):
    parts = str(value).split(":")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        return False
    return 0 <= int(parts[0]) <= 23 and 0 <= int(parts[1]) <= 59


def validate_update(fields):
    """{field: plain-English error} for every invalid value in `fields`
    (None values are ignored, same as update()). Empty dict = valid."""
    errors = {}
    for key, value in fields.items():
        if value is None:
            continue
        if key in _NUMERIC_RULES:
            kind, lo, hi, lo_inclusive = _NUMERIC_RULES[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
                errors[key] = "must be a number"
                continue
            if kind == "int" and int(value) != value:
                errors[key] = "must be a whole number"
                continue
            if lo is not None and (value < lo if lo_inclusive else value <= lo):
                errors[key] = f"must be {'at least' if lo_inclusive else 'greater than'} {lo}"
            elif hi is not None and value > hi:
                errors[key] = f"must be at most {hi}"
        elif key == "priority_rule" and value not in _PRIORITY_RULES:
            errors[key] = f"must be one of: {', '.join(sorted(_PRIORITY_RULES))}"
        elif key == "opposite_signal_policy" and value not in _OPPOSITE_POLICIES:
            errors[key] = f"must be one of: {', '.join(sorted(_OPPOSITE_POLICIES))}"
        elif key in ("time_filter_block_start_utc", "time_filter_block_end_utc") and not _valid_hhmm(value):
            errors[key] = "must be a time in HH:MM (24-hour) format"
    return errors


def defaults():
    return dict(_DEFAULTS)


_HISTORY_KEY = "paper_trading_settings_history"
_HISTORY_FILE = "paper_trading_settings_history.json"
HISTORY_KEEP_LAST = 200


def load_history():
    """Newest first. Stored via load_persistent, so the cloud keeps its
    history in Postgres (not the ephemeral local disk) -- the same
    local-file-vs-cloud-database split every other setting here uses."""
    data = base_config.load_persistent(_HISTORY_KEY, _HISTORY_FILE, {"entries": []})
    return list(data.get("entries", []))


def record_change(before, after, source="dashboard"):
    """Appends one history entry listing every field whose value actually
    changed; a save that changed nothing records nothing. Returns the
    entry, or None."""
    changes = [
        {"field": k, "old": before.get(k), "new": after.get(k)}
        for k in sorted(after) if before.get(k) != after.get(k)
    ]
    if not changes:
        return None
    entry = {"changed_at": datetime.now(timezone.utc).isoformat(), "source": source, "changes": changes}
    entries = [entry] + load_history()
    base_config.save_persistent(_HISTORY_KEY, _HISTORY_FILE, {"entries": entries[:HISTORY_KEEP_LAST]})
    return entry
