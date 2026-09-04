"""Master Task 3, Phase 2.9 (Multiple Simultaneous Challenges) + 2.4
(multi-timeframe targets) + 2.15 (compound vs fixed-risk) + 2.18 (custom
deadline flexibility) + 2.20 (achievability score trend).

A genuinely separate, independently-queryable challenge per row (the
`challenges` table, data_engine/storage.py) -- distinct from paper_trading.
challenge_mode's original single-challenge JSON/cloud_setting, which is
left completely untouched so the existing embedded Paper Trading widget
and Telegram's challenge-scope signal tagging keep working exactly as
before. Every actual progress/rate calculation reuses challenge_mode.
compute_progress() (now settings-injectable, see its own docstring) --
this module only adds the "more than one, with a timeframe label and a
compounding choice" layer on top, never re-derives the math.

Read-only/tracking, same boundary every Challenge Mode module documents:
never touches risk_pct, position sizing, or any trading behavior.
"""

import uuid
from datetime import datetime, timezone

from data_engine import storage
from paper_trading import challenge_mode

TIMEFRAME_DAYS = {"daily": 1, "weekly": 7, "monthly": 30}
MAX_ACTIVE_CHALLENGES = 3


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def create_challenge(
    label, start_amount, target_amount, timeframe_type, days=None,
    scope_strategy_id=None, scope_symbol=None, telegram_report_enabled=False, compounding=True,
):
    """Phase 2.4: timeframe_type is one of 'daily'/'weekly'/'monthly'
    (days derived automatically) or 'custom' (an explicit `days` is
    required). Phase 2.9: refuses a 4th active challenge outright rather
    than silently degrading tracking quality for all of them -- 2-3 at
    once is the explicit ask, not unlimited."""
    if timeframe_type not in ("daily", "weekly", "monthly", "custom"):
        raise ValueError(f"unknown timeframe_type: {timeframe_type}")
    if timeframe_type == "custom":
        if not days or days <= 0:
            raise ValueError("days is required and must be positive for timeframe_type='custom'")
    else:
        days = TIMEFRAME_DAYS[timeframe_type]

    active = storage.list_challenges()
    if len(active) >= MAX_ACTIVE_CHALLENGES:
        raise ValueError(
            f"already tracking {MAX_ACTIVE_CHALLENGES} active challenges -- archive one before starting another"
        )
    if start_amount is None or target_amount is None:
        raise ValueError("start_amount and target_amount are required")
    start_amount, target_amount = float(start_amount), float(target_amount)
    if start_amount <= 0:
        raise ValueError("start_amount must be positive")

    baseline_win_rate_pct = None
    if scope_strategy_id and scope_symbol:
        from paper_trading import challenge_analysis
        rows = challenge_analysis._closed_rows(scope_strategy_id, scope_symbol)
        if rows:
            wins = sum(1 for r in rows if r["pnl"] > 0)
            baseline_win_rate_pct = round(wins / len(rows) * 100, 2)

    challenge_id = uuid.uuid4().hex[:12]
    now = _now_iso()
    storage.create_challenge(
        challenge_id, label, start_amount, target_amount, timeframe_type, days, now, now,
        scope_strategy_id=scope_strategy_id, scope_symbol=scope_symbol,
        baseline_win_rate_pct=baseline_win_rate_pct,
        telegram_report_enabled=telegram_report_enabled, compounding=compounding,
    )
    return storage.get_challenge(challenge_id)


def extend_deadline(challenge_id, new_days):
    """Phase 2.18: extend or shorten a challenge's deadline in place --
    started_at and everything already achieved stays exactly as it was,
    only the target date recalculates live on the next progress read."""
    if new_days <= 0:
        raise ValueError("new_days must be positive")
    if not storage.get_challenge(challenge_id):
        raise ValueError(f"unknown challenge id: {challenge_id}")
    storage.update_challenge(challenge_id, _now_iso(), days=new_days, timeframe_type="custom")
    return storage.get_challenge(challenge_id)


def archive_challenge(challenge_id):
    storage.archive_challenge(challenge_id, _now_iso())


def _as_progress_settings(row):
    return {
        "enabled": True, "start_amount": row["start_amount"], "target_amount": row["target_amount"],
        "days": row["days"], "started_at": row["started_at"],
        "scope_strategy_id": row["scope_strategy_id"], "scope_symbol": row["scope_symbol"],
        "baseline_win_rate_pct": row["baseline_win_rate_pct"],
        "telegram_report_enabled": row["telegram_report_enabled"],
    }


def compute_progress_for(challenge_id, now_iso=None):
    """One challenge's full progress dict (challenge_mode.compute_progress's
    exact shape) plus its own label/timeframe/compounding -- None if the
    challenge doesn't exist or has been archived."""
    row = storage.get_challenge(challenge_id)
    if not row or row["archived"]:
        return None
    progress = challenge_mode.compute_progress(now_iso=now_iso, settings=_as_progress_settings(row))
    if progress is None:
        return None
    progress.update({
        "challenge_id": challenge_id, "label": row["label"], "timeframe_type": row["timeframe_type"],
        "compounding": row["compounding"],
    })
    return progress


def compute_all_progress(now_iso=None):
    """Phase 2.9's side-by-side view: every active challenge's progress at
    once, same instant."""
    return [compute_progress_for(c["id"], now_iso=now_iso) for c in storage.list_challenges()]


def compute_compounding_current_amount(challenge_id):
    """Phase 2.15: what the SAME real trades would have produced if risk
    compounded with the account (grows with balance) instead of staying a
    fixed dollar amount off the original start_amount -- challenge_mode.
    compute_progress()'s own current_amount is already the fixed-risk
    figure (risk_per_trade is computed once from start_amount and never
    changes), so this is the one genuinely new calculation Phase 2.15
    needs, not a duplicate.

    Returns (compounding_amount, fixed_risk_amount, trades_counted) so the
    two can be shown side by side."""
    from paper_trading import challenge_analysis, config as pt_config

    row = storage.get_challenge(challenge_id)
    if not row or row["archived"]:
        return None
    risk_pct = pt_config.load().get("risk_pct_default", 1.0) / 100.0

    if row["scope_strategy_id"] and row["scope_symbol"]:
        rows = challenge_analysis._closed_rows(row["scope_strategy_id"], row["scope_symbol"])
    else:
        rows = challenge_analysis._closed_rows()
    trades = sorted(
        (t for t in rows if t.get("closed_at") and t["closed_at"] >= row["started_at"] and t.get("risk_amount")),
        key=lambda t: t["closed_at"],
    )

    compounding_balance = row["start_amount"]
    fixed_risk_per_trade = row["start_amount"] * risk_pct
    fixed_balance = row["start_amount"]
    for t in trades:
        r_multiple = t["pnl"] / t["risk_amount"]
        compounding_balance += r_multiple * (compounding_balance * risk_pct)
        fixed_balance += r_multiple * fixed_risk_per_trade

    return {
        "compounding_amount": round(compounding_balance, 2),
        "fixed_risk_amount": round(fixed_balance, 2),
        "trades_counted": len(trades),
    }


def record_achievability_snapshot(challenge_id):
    """Phase 2.20: samples the current achievability into a percentage
    score (0 if not realistic at all, 100 if already at/ahead of target,
    otherwise how close the real demonstrated pace is to the required
    pace) and persists it -- called periodically by the scheduler thread
    below, building up the real history a 7-day trend line needs."""
    progress = compute_progress_for(challenge_id)
    if progress is None:
        return None
    if progress["progress_pct"] >= 100.0:
        score = 100.0
    elif progress["real_demonstrated_daily_rate_pct"] is None or progress["required_daily_rate_pct"] <= 0:
        score = 0.0
    else:
        required = progress["required_daily_rate_pct"]
        real = progress["real_demonstrated_daily_rate_pct"]
        score = round(max(0.0, min(100.0, (real / required) * 100)), 2) if required > 0 else 100.0
    storage.record_challenge_achievability_snapshot(challenge_id, score, _now_iso())
    return score


def achievability_trend(challenge_id, days=7):
    """Phase 2.20: the real recorded snapshot history over the last `days`
    days -- an honest 'improving vs worsening' trend, not just a single
    current snapshot. Empty list (not an error) if snapshotting has not
    run long enough yet to have any history."""
    from datetime import timedelta
    since_iso = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    return storage.list_challenge_achievability_snapshots(challenge_id, since_iso=since_iso)


def start_achievability_snapshot_scheduler_thread():
    """Runs once at server startup; snapshots every active challenge's
    achievability every few hours -- frequent enough for a meaningful
    7-day trend without hammering the database."""
    import threading
    import time
    from data_engine.logging_setup import log

    def _loop():
        while True:
            try:
                for c in storage.list_challenges():
                    record_achievability_snapshot(c["id"])
            except Exception as e:
                log(f"[challenge-achievability] snapshot sweep failed: {e!r}")
            time.sleep(4 * 3600)

    threading.Thread(target=_loop, daemon=True).start()
