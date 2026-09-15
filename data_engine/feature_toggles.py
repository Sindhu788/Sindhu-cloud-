"""Centralized on/off state for SINDHU's automated background features
(the dashboard's Feature Control Center) -- a visibility/control layer
only. Each flag is read at the exact call site the feature already ran
from; turning a flag off just skips that specific future call, it never
touches an already-open position, already-written history, or the
Paper Trading engine's own start/stop state.

Master Task Grand Batch, Phase 2.2 bug fix: uses config.load_persistent/
save_persistent (Postgres-aware on the cloud deployment, see their
docstrings) instead of the plain JSON-file load_or_seed/save_config this
module used before -- on Render the local file is wiped every restart/
redeploy/sleep-wake, so a toggle flipped from the dashboard while running
on Postgres would silently revert to these defaults on the next restart.
"""

from data_engine import config

_FILE = "feature_toggles.json"
_CLOUD_KEY = "feature_toggles"

DEFAULTS = {
    "master_pause_all": False,
    "auto_avoid_enabled": True,
    "lesson_auto_apply_enabled": True,
    "drawdown_protection_enabled": True,
    "dynamic_risk_sizing_enabled": True,
    "capital_allocation_enabled": True,
    "backup_enabled": True,
    "weekly_report_enabled": True,
    "monthly_report_enabled": True,
    "strategy_lab_enabled": True,
    "sindhu_strategy_autogen_enabled": True,
    # Grand Feature Expansion, Phase 5 Feature 8: Slippage-Aware Entry
    # Filter -- rejects a real entry whose estimated slippage would eat too
    # much of its own stop distance (a realistic missed/adverse-fill risk
    # protection). Was off by default pending CEO review; Grand Master
    # Batch #2, Phase 1.2 explicitly asked for paper trading to stop
    # assuming a perfect fill and account for missed-fill scenarios, so
    # this is now on by default -- always risk-REDUCING (only ever rejects
    # a trade that would otherwise open, never opens one that wouldn't
    # have). NOTE: this only changes the DEFAULT for an install that never
    # explicitly saved this key -- if it was ever explicitly toggled off
    # from the dashboard, that persisted value still wins (same
    # load_persistent "saved value wins" rule every other setting in this
    # app follows) and needs flipping back on from the Control Center.
    "slippage_aware_filter_enabled": True,
    # Grand Feature Expansion, Phase 5 Feature 10: Ensemble Voting
    # Confirmation -- requires agreement from a minimum number of
    # INDEPENDENT strategies on the same symbol+direction within the same
    # tick before any of them can open. Always risk-REDUCING (only makes
    # trading more conservative), but still a brand-new gate -- off by
    # default like the other new Phase 5 gates above.
    "ensemble_voting_enabled": False,
    # Grand Feature Expansion, Phase 6 Feature 13: Automated Weekly
    # Strategy Review -- a pure reporting/notification feature (never
    # touches a trade or a mutation decision), same category as
    # weekly_report_enabled/monthly_report_enabled above, so it defaults
    # True like they do.
    "evolution_weekly_review_enabled": True,
    # Grand Feature Expansion, Phase 7 Feature 10: Automated Weekly
    # Digest -- a pure reporting/notification feature (system health only,
    # never touches a trade or mutation decision), same category as the
    # other weekly report toggles above, so it defaults True like they do.
    "infra_weekly_digest_enabled": True,
    # Master Task 3, Phase 1: Self-Learning Engine -- discovers brand-new
    # candidate strategies (concept combinations) and, if one genuinely
    # passes the mandatory out-of-sample gate, saves it to the strategy
    # library. Same category as sindhu_strategy_autogen_enabled above: it
    # only ever creates a LIBRARY entry, never enables live/paper trading
    # by itself (a separate, explicit "Move to Paper Trading" action is
    # always required after, same safety gate every strategy goes
    # through) -- so it defaults True like that existing generator does.
    "self_learning_engine_enabled": True,
}


def get_toggles():
    return config.load_persistent(_CLOUD_KEY, _FILE, DEFAULTS)


def set_toggle(key, value):
    if key not in DEFAULTS:
        raise ValueError(f"unknown feature toggle: {key}")
    data = get_toggles()
    data[key] = bool(value)
    config.save_persistent(_CLOUD_KEY, _FILE, data)
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
