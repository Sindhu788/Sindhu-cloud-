"""Per-strategy cooling-off period (2026-09-16 audit, CEO Section 10.1).

After `cooling_off_loss_streak` consecutive losing trades, that ONE strategy
opens no new positions for `cooling_off_hours`, counted from its most recent
losing close -- then it resumes on its own. Existing open positions are
never touched (same scope as every other pre-entry guard).

How this differs from what already existed:
  - drawdown_guard.py pauses a strategy at a LONGER streak (default 7) and
    stays paused until the CEO clicks Resume -- untouched by this module.
  - guards.cooldown_active() blocks re-entering the same coin+direction for
    a few minutes after ANY close -- also untouched.
This is a shorter, self-expiring pause in between. It only ever ADDS a
reason not to open a trade; it never loosens or overrides any other gate.

Stateless: derived from the strategy's own closed-trade history on every
check (no new table, no flag to get stuck), so it behaves identically on
the local SQLite app and the cloud Postgres runner and survives restarts.
Set cooling_off_loss_streak to 0 to turn it off."""

from datetime import datetime, timedelta, timezone

from data_engine import storage

DEFAULT_LOSS_STREAK = 4
DEFAULT_HOURS = 3.0


def _parse(iso):
    try:
        dt = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def check(strategy_id, settings, now=None):
    """(active, reason, until_iso). active=False whenever disabled, the
    strategy has fewer than `streak` closed trades, any of its latest
    `streak` trades was not a loss, or the cooling-off window has passed."""
    streak = int(settings.get("cooling_off_loss_streak", DEFAULT_LOSS_STREAK) or 0)
    hours = float(settings.get("cooling_off_hours", DEFAULT_HOURS) or 0)
    if not strategy_id or streak <= 0 or hours <= 0:
        return False, None, None
    recent = storage.list_recent_closed_pnls(strategy_id, streak)
    if len(recent) < streak or any(r["pnl"] >= 0 for r in recent):
        return False, None, None
    last_loss_at = _parse(recent[0]["closed_at"])
    if last_loss_at is None:
        return False, None, None
    until = last_loss_at + timedelta(hours=hours)
    now = now or datetime.now(timezone.utc)
    if now >= until:
        return False, None, None
    reason = (f"cooling-off: {streak} consecutive losses -- no new entries for this strategy "
              f"until {until.strftime('%Y-%m-%d %H:%M')} UTC")
    return True, reason, until.isoformat()
