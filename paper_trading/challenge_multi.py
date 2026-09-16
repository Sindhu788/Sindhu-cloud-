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
    if scope_strategy_id or scope_symbol:  # see challenge_mode.compute_progress's own `scoped` comment
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


def is_active_challenge_signal(strategy_id, symbol):
    """Part 4, 4.1: does this signal belong to a user-created, currently
    active (not archived, not paused) challenge? Used by telegram_bot.
    format_signal_message to attach the distinct ⚫ marker alongside the
    existing 🔵/🔴/🟣 group markers -- a challenge's scoped strategy+coin
    is a SEPARATE, additive classification from strategy_groups' own
    profitable/losing/challenge-GROUP buckets, so a signal can (and
    often will) show both markers at once."""
    if not strategy_id or not symbol:
        return False
    for c in storage.list_challenges():
        if c["paused"]:
            continue
        if c["scope_strategy_id"] == strategy_id and c["scope_symbol"] == symbol:
            return True
    return False


# --------------------------------------------------------------- Telegram /challenge command (2026-09-17)

BALANCE_PAUSE_THRESHOLD_PCT = 50.0  # 2.5: pause + warn once current_amount drops this far below start


def find_non_conflicting_path(paths, exclude_archived=True):
    """2.12 (resource conflicts): a (strategy_id, symbol) combo already
    claimed as another ACTIVE challenge's exact scope would have its real
    trades counted toward BOTH challenges' targets at once -- the same
    real money "used twice". Returns the first path (already ranked by
    recommend_paths -- best first) whose combo isn't already claimed, or
    None if every candidate is already claimed."""
    claimed = {
        (c["scope_strategy_id"], c["scope_symbol"])
        for c in storage.list_challenges(include_archived=not exclude_archived)
        if c["scope_strategy_id"] and c["scope_symbol"]
    }
    for p in paths:
        if (p["strategy_id"], p["symbol"]) not in claimed:
            return p
    return None


def check_balance_threshold(challenge_id, threshold_pct=BALANCE_PAUSE_THRESHOLD_PCT, now_iso=None):
    """2.5: if a challenge's current_amount has dropped below threshold_pct
    of its start_amount, pause it (paused=True -- NOT archived: paper
    trading and every other challenge continue completely unaffected,
    this only marks this one challenge for a human decision) and return
    the info needed for a warning message. Returns None when there's
    nothing new to warn about (not below threshold, already paused, or
    already archived)."""
    row = storage.get_challenge(challenge_id)
    if not row or row["archived"] or row["paused"]:
        return None
    progress = compute_progress_for(challenge_id, now_iso=now_iso)
    if progress is None:
        return None
    threshold_amount = row["start_amount"] * (threshold_pct / 100.0)
    if progress["current_amount"] >= threshold_amount:
        return None
    storage.update_challenge(challenge_id, now_iso or _now_iso(), paused=True)
    return {
        "challenge_id": challenge_id, "label": row["label"],
        "start_amount": row["start_amount"], "current_amount": progress["current_amount"],
        "threshold_pct": threshold_pct,
    }


def resume_challenge(challenge_id, now_iso=None):
    """The "continue" half of 2.5's warning -- explicitly un-pauses a
    challenge the CEO decided to keep running as-is."""
    row = storage.get_challenge(challenge_id)
    if not row:
        raise ValueError(f"unknown challenge id: {challenge_id}")
    storage.update_challenge(challenge_id, now_iso or _now_iso(), paused=False)
    return storage.get_challenge(challenge_id)


def stop_challenge(challenge_id, now_iso=None):
    """2.10 (/stopchallenge): manually ends a challenge early. Whatever
    the result is at this exact moment becomes final -- archived with
    final_status='stopped', same as a natural completion/failure, so it
    shows up in history (2.14) honestly labeled as CEO-ended rather than
    a real completion or a real deadline failure."""
    row = storage.get_challenge(challenge_id)
    if not row:
        raise ValueError(f"unknown challenge id: {challenge_id}")
    if row["archived"]:
        raise ValueError(f"challenge {challenge_id} is already archived (final_status={row['final_status']})")
    progress = compute_progress_for(challenge_id, now_iso=now_iso)
    now_iso = now_iso or _now_iso()
    storage.update_challenge(challenge_id, now_iso, archived=1, final_status="stopped")
    return progress


def celebration_summary(challenge_id):
    """2.13: a genuine completion deserves more than "complete" -- days
    taken, signals actually sent for this challenge, best/worst real
    trade, and a real profit factor, all computed from this challenge's
    own scoped real trades since it started (unscoped challenges use
    every real trade system-wide since start, same convention
    compute_progress already uses)."""
    row = storage.get_challenge(challenge_id)
    if not row:
        return None
    from paper_trading import challenge_analysis
    rows = [
        t for t in challenge_analysis._closed_rows(row["scope_strategy_id"], row["scope_symbol"])
        if t.get("closed_at") and t["closed_at"] >= row["started_at"]
    ]
    days_taken = None
    if rows:
        started = datetime.fromisoformat(row["started_at"])
        last_close = datetime.fromisoformat(max(t["closed_at"] for t in rows))
        days_taken = round((last_close - started).total_seconds() / 86400, 2)
    gains = sum(t["pnl"] for t in rows if t["pnl"] > 0)
    losses = sum(-t["pnl"] for t in rows if t["pnl"] < 0)
    profit_factor = round(gains / losses, 2) if losses > 0 else (None if not rows else float("inf"))
    best_trade = max(rows, key=lambda t: t["pnl"]) if rows else None
    worst_trade = min(rows, key=lambda t: t["pnl"]) if rows else None
    return {
        "challenge_id": challenge_id, "label": row["label"],
        "start_amount": row["start_amount"], "target_amount": row["target_amount"],
        "days_taken": days_taken, "signals_used": len(rows),
        "profit_factor": profit_factor,
        "best_trade": {"symbol": best_trade["symbol"], "pnl": round(best_trade["pnl"], 2)} if best_trade else None,
        "worst_trade": {"symbol": worst_trade["symbol"], "pnl": round(worst_trade["pnl"], 2)} if worst_trade else None,
    }


def sweep_challenge_lifecycle(now_iso=None):
    """Runs periodically (see the scheduler thread below): for every
    active, non-paused challenge, checks in order -- (1) genuinely
    completed (2.13's celebration), (2) deadline expired without hitting
    the target (2.6's honest failure), (3) balance dropped below the
    safe threshold (2.5's pause+warn). A challenge that just got paused
    this same tick is skipped for the completed/failed checks below it
    (an already-paused challenge is left for the CEO to resume or
    /stopchallenge, not auto-archived out from under them).

    Returns a list of {"kind": "completed"|"failed"|"paused", **details}
    -- the Telegram sender (paper_trading.telegram_challenge_commands)
    turns each into the right message; this function only detects real
    state transitions and persists them, it never sends anything itself,
    same read/write vs. send separation every other module here keeps."""
    now_iso = now_iso or _now_iso()
    events = []
    for row in storage.list_challenges():
        if row["paused"]:
            continue
        progress = compute_progress_for(row["id"], now_iso=now_iso)
        if progress is None:
            continue
        if progress["progress_pct"] >= 100.0:
            summary = celebration_summary(row["id"])
            storage.update_challenge(row["id"], now_iso, archived=1, final_status="completed")
            events.append({"kind": "completed", **summary})
            continue
        if progress["remaining_days"] <= 0:
            storage.update_challenge(row["id"], now_iso, archived=1, final_status="failed")
            events.append({
                "kind": "failed", "challenge_id": row["id"], "label": row["label"],
                "progress_pct": progress["progress_pct"], "current_amount": progress["current_amount"],
                "target_amount": row["target_amount"], "days": row["days"],
            })
            continue
        paused_info = check_balance_threshold(row["id"], now_iso=now_iso)
        if paused_info:
            events.append({"kind": "paused", **paused_info})
    return events


def list_challenge_history(limit=20):
    """2.14: completed/failed/stopped challenges, most recent first."""
    rows = [c for c in storage.list_challenges(include_archived=True) if c["archived"]]
    rows.sort(key=lambda c: c["updated_at"], reverse=True)
    return rows[:limit]


def send_daily_challenge_updates(now_iso=None):
    """2.15: a daily auto-update for each active challenge, without being
    asked -- today's result, running total, % of target reached. Dedupes
    against last_daily_update_sent_at so a scheduler tick running more
    than once doesn't double-send the same UTC day's update."""
    from paper_trading import telegram_bot
    now_iso = now_iso or _now_iso()
    today = now_iso[:10]
    sent = []
    for row in storage.list_challenges():
        if (row["last_daily_update_sent_at"] or "")[:10] == today:
            continue
        progress = compute_progress_for(row["id"], now_iso=now_iso)
        if progress is None:
            continue
        settings = telegram_bot.load_settings()
        if not settings.get("bot_token") or not settings.get("channel_id"):
            continue
        label = row["label"] or row["id"]
        status_word = "PAUSED" if row["paused"] else ("ahead of pace" if progress["ahead_of_pace"] else "behind pace")
        text = (
            f"\U0001F4C5 Daily update -- {label}\n"
            f"${progress['current_amount']:.2f} of ${progress['target_amount']:.2f} target "
            f"({progress['progress_pct']:.1f}%), {progress['remaining_days']:.1f} days left, {status_word}."
        )
        ok, _error = telegram_bot._raw_send(text)
        if ok:
            storage.update_challenge(row["id"], now_iso, last_daily_update_sent_at=now_iso)
            sent.append(row["id"])
    return sent


def start_challenge_lifecycle_scheduler_thread():
    """Runs once at server startup (see sindhu_web/server.py and
    cloud_runtime/app.py): sweeps completed/failed/paused transitions
    every 15 minutes (frequent enough that a genuine completion or a
    balance-threshold breach gets a timely message, not a multi-hour-old
    one), and sends the once-a-day per-challenge update on the same loop
    (send_daily_challenge_updates is itself idempotent per UTC day, so
    running it every 15 minutes just means it fires within 15 minutes of
    a new UTC day starting, not more than once)."""
    import threading
    import time
    from data_engine.logging_setup import log

    def _loop():
        while True:
            try:
                events = sweep_challenge_lifecycle()
                if events:
                    from paper_trading import telegram_challenge_commands
                    telegram_challenge_commands.send_lifecycle_event_messages(events)
                send_daily_challenge_updates()
            except Exception as e:
                log(f"[challenge-lifecycle] sweep failed: {e!r}")
            time.sleep(15 * 60)

    threading.Thread(target=_loop, daemon=True).start()


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
