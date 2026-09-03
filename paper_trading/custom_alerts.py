"""Custom Alert Rules (Grand Feature Expansion, Phase 4 Feature 25): a
user-DEFINED "alert me if X happens" mechanism, distinct from every other
alert in this system (paper_alerts is 100% system-generated -- drawdown,
streaks, implausible backtests, etc).

Deliberately bounded, not a general rule engine: `metric` is always one of
a small, fixed, validated set (METRIC_CHOICES below) evaluated by trusted
Python code already used elsewhere in this codebase -- never an arbitrary
user-supplied expression, so this can never become an injection surface or
run arbitrary logic. A rule that isn't one of these metrics is rejected
outright, not silently ignored.
"""

import uuid
from datetime import datetime, timedelta, timezone

from data_engine import storage
from paper_trading import account_drawdown_guard, insights

METRIC_CHOICES = ("strategy_pnl", "strategy_win_rate", "consecutive_losses", "account_drawdown_pct")
COMPARISON_CHOICES = ("below", "above")

# Same reasoning as every other throttled sweep in this codebase (Telegram
# retry, win-rate decay, divergence): don't re-alert the same rule every
# single sweep once it's already been flagged recently.
RECHECK_HOURS = 6


def create_rule(name, metric, comparison, threshold, strategy_id=None):
    if metric not in METRIC_CHOICES:
        raise ValueError(f"metric must be one of {METRIC_CHOICES}")
    if comparison not in COMPARISON_CHOICES:
        raise ValueError(f"comparison must be one of {COMPARISON_CHOICES}")
    if metric != "account_drawdown_pct" and not strategy_id:
        raise ValueError(f"metric '{metric}' requires a strategy_id")
    rule_id = uuid.uuid4().hex[:12]
    storage.create_custom_alert_rule(
        rule_id, name, metric, strategy_id, comparison, threshold,
        datetime.now(timezone.utc).isoformat(),
    )
    return rule_id


def list_rules():
    return storage.list_custom_alert_rules()


def delete_rule(rule_id):
    storage.delete_custom_alert_rule(rule_id)


def set_rule_enabled(rule_id, enabled):
    storage.set_custom_alert_rule_enabled(rule_id, enabled)


def _current_value(rule):
    """Returns the metric's current real value, or None if there isn't
    enough data yet to evaluate it honestly (never fabricates a number)."""
    metric = rule["metric"]
    if metric == "strategy_pnl":
        return storage.get_paper_account_summary(rule["strategy_id"])["realized_pnl_total"]
    if metric == "strategy_win_rate":
        summary = storage.get_paper_account_summary(rule["strategy_id"])
        if summary["closed_count"] == 0:
            return None
        return summary["win_count"] / summary["closed_count"] * 100
    if metric == "consecutive_losses":
        streak = insights.compute_streak(rule["strategy_id"])
        return streak["count"] if streak["type"] == "loss" else 0
    if metric == "account_drawdown_pct":
        return account_drawdown_guard.status()["drawdown_pct"]
    return None


def _breaches(rule, value):
    if rule["comparison"] == "below":
        return value < rule["threshold"]
    return value > rule["threshold"]


def sweep_custom_alert_rules():
    """Checks every enabled rule, creating one paper_alerts entry per rule
    that currently breaches its threshold -- throttled to once per
    RECHECK_HOURS per rule so an ongoing breach doesn't spam."""
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    triggered = []
    for rule in storage.list_custom_alert_rules(enabled_only=True):
        if rule["last_triggered_at"]:
            last = datetime.fromisoformat(rule["last_triggered_at"])
            if now - last < timedelta(hours=RECHECK_HOURS):
                continue
        value = _current_value(rule)
        if value is None or not _breaches(rule, value):
            continue
        message = (
            f"Custom alert \"{rule['name']}\": {rule['metric']} is {round(value, 2)}, "
            f"{rule['comparison']} your threshold of {rule['threshold']}."
        )
        storage.create_paper_alert("custom_rule", rule["strategy_id"], rule["name"], message, "warning", now_iso)
        storage.mark_custom_alert_rule_triggered(rule["id"], now_iso)
        triggered.append(rule["id"])
    return triggered
