"""Honest delivery reporting for Telegram signals.

The point of this module is a single, strict rule: a signal is only ever
reported as "Sent" if a real successful send was actually recorded for it.
Everything else says, in plain words, what genuinely happened instead --
withheld by a gate, blocked by the network, never attempted. Nothing here
sends, re-sends, or retries anything; it is a read-only view over what the
rest of the system already recorded.

Why this exists separately from telegram_bot.py: api.telegram.org is
blocked at the network level in the CEO's region, so most signals the
system generates are never delivered at all. A report driven off
telegram_message_log alone can only ever show signals that were ATTEMPTED,
which would make the channel look far quieter and far healthier than it is.
This module starts from every signal that was GENERATED (every paper
position opened) and works forwards to what became of it.

It also keeps the delivery-reporting logic out of telegram_bot.py, which
owns actual sending -- so the reporting side stays usable, testable, and
deployable on its own even where sending cannot work.
"""

from datetime import datetime, timezone

from data_engine import storage
from paper_trading import telegram_bot


# One row per delivery state. `STATUS_LABELS` is the single vocabulary the
# whole product uses for "what happened to this signal" -- the dashboard
# renders these strings directly rather than inventing its own wording.
STATUS_LABELS = {
    "sent": "Sent",
    "blocked_network": "Failed -- network blocked",
    "failed_telegram": "Failed -- Telegram rejected it",
    "withheld_stale": "Withheld -- stale (freshness gate)",
    "withheld_drift": "Withheld -- price moved away (freshness gate)",
    "withheld_switch": "Withheld -- sending is turned off",
    "withheld_rate_limit": "Withheld -- hourly limit reached",
    "not_configured": "Not sent -- Telegram not set up",
    "queued": "Queued",
    "never_sent": "Never sent",
}

# Connection-level failure shapes that mean "the request never reached
# Telegram", as opposed to Telegram answering with a refusal. These are the
# exact exception names requests raises through telegram_bot._raw_send's
# repr(e), plus the wrapper text that function adds after exhausting its
# retries.
_NETWORK_MARKERS = (
    "connectionerror", "proxyerror", "readtimeout", "connecttimeout",
    "sslerror", "maxretryerror", "newconnectionerror", "failed after",
)


def classify_attempt(attempt):
    """Turn one telegram_message_log row into a status id. Reads only what
    was actually recorded at the time -- never guesses, never re-checks."""
    if attempt.get("success"):
        return "sent"
    err = (attempt.get("error") or "").lower()
    if "too stale" in err:
        return "withheld_stale"
    if "moved more than" in err or "opportunity has likely already passed" in err:
        return "withheld_drift"
    if "master switch" in err or "turned off" in err:
        return "withheld_switch"
    if "rate limit" in err:
        return "withheld_rate_limit"
    if "not configured" in err:
        return "not_configured"
    if any(marker in err for marker in _NETWORK_MARKERS):
        return "blocked_network"
    return "failed_telegram"


def classify_signal(signal, auto_send_enabled):
    """The delivery status of one GENERATED signal.

    A signal with no attempt at all is the common case while Telegram is
    blocked, and the two honest answers differ: if the position is still
    open AND auto-send is on, the recurring sweep really will re-evaluate
    it (telegram_bot.sweep_unsent_qualifying_signals), so "Queued" is a
    true statement about a real pending re-check. Once the position has
    closed, or if auto-send is off, nothing will ever pick it up again --
    that is "Never sent", not "Queued".
    """
    attempts = signal.get("attempts") or []
    if attempts:
        # A single successful send is the whole story regardless of what
        # failed before it -- a signal that eventually got through was
        # delivered, and saying otherwise would understate the channel.
        if any(a.get("success") for a in attempts):
            return "sent"
        return classify_attempt(attempts[0])  # newest attempt, already sorted
    if signal.get("status") == "open" and auto_send_enabled:
        return "queued"
    return "never_sent"


def _outcome(signal):
    """The real trading result of the trade this signal corresponded to --
    straight from the recorded position, never inferred. A trade still open
    is always 'pending', never guessed at."""
    if signal.get("status") == "open":
        return "pending"
    pnl = signal.get("pnl")
    if signal.get("status") == "closed" and pnl is not None:
        return "win" if pnl > 0 else "loss" if pnl < 0 else "breakeven"
    return "unknown"


def delivery_rows(signals, auto_send_enabled=None):
    """Decorate raw rows from storage.list_generated_signals_with_delivery
    with their delivery status, label, and real trade outcome."""
    if auto_send_enabled is None:
        auto_send_enabled = bool(telegram_bot.load_settings().get("auto_send_enabled", False))
    rows = []
    for s in signals:
        status = classify_signal(s, auto_send_enabled)
        attempts = s.get("attempts") or []
        latest = attempts[0] if attempts else None
        rows.append({
            "position_id": s["id"],
            "generated_at": s.get("created_at"),
            "strategy_id": s.get("strategy_id"),
            "strategy_name": s.get("strategy_name"),
            "symbol": s.get("symbol"),
            "direction": s.get("direction"),
            "entry_price": s.get("entry_price"),
            "stop_loss": s.get("stop_loss"),
            "take_profit": s.get("take_profit"),
            "confidence": s.get("confidence"),
            "quality_grade": latest.get("quality_grade") if latest else None,
            "delivery_status": status,
            "delivery_label": STATUS_LABELS[status],
            # The verbatim recorded reason, so the screen can show exactly
            # why rather than a rounded-off category.
            "delivery_detail": (latest or {}).get("error"),
            "last_attempt_at": (latest or {}).get("sent_at"),
            "attempt_count": len(attempts),
            "outcome": _outcome(s),
            "pnl": s.get("pnl"),
        })
    return rows


def connection_status():
    """Is Telegram delivery actually working right now, and if not, why.

    Moved here (Grand Master Batch, Phase 3) from sindhu_web/api/paper_
    trading.py's get_telegram_connection_status() route, which now just
    calls this and returns its result unchanged -- so the System Health
    Score can use the exact same real "state" without importing the web
    layer from paper_trading (that would invert this package's dependency
    direction and risk a circular import once the web layer imports the
    health-score module too).

    Deliberately makes NO network call: it reads the configuration plus
    what the real send attempts already recorded. A live probe on every
    page load would add a multi-second stall to a page whose whole point is
    to remain useful while the network is blocked. The Test Connection
    button (POST /telegram/test) is the deliberate live check."""
    settings = telegram_bot.public_settings()
    recent = storage.list_telegram_messages(limit=40)
    real = [m for m in recent if m["trigger_type"] in ("manual", "automatic", "daily_report")]
    last_success = next((m for m in real if m["success"]), None)
    last_failure = next((m for m in real if not m["success"]), None)

    if not settings["token_configured"] or not settings["channel_id"]:
        state, reason = "not_configured", "No bot token or channel ID has been saved yet."
    elif not settings["master_send_enabled"]:
        state, reason = "turned_off", "Sending is switched off, so nothing is being delivered on purpose."
    elif last_success and (not last_failure or last_success["sent_at"] > last_failure["sent_at"]):
        state = "working"
        # Name WHAT last got through. The most recent success is very often
        # a scheduled daily report rather than a trade signal, and "delivery
        # is working" sitting directly above "no signals sent in 4 weeks"
        # reads as a contradiction unless the difference is spelled out.
        # Both statements are true; this makes them legible together.
        kind = ("a scheduled daily report" if last_success["trigger_type"] == "daily_report"
                else "a trade signal")
        reason = (f"The connection itself is fine -- {kind} was delivered successfully on "
                  f"{last_success['sent_at'][:16].replace('T', ' ')}. That does not mean any trade "
                  f"signals have gone out recently; the signal log below is what says that.")
    elif last_failure:
        status_id = classify_attempt(last_failure)
        if status_id == "blocked_network":
            state = "blocked"
            reason = ("The request never reached Telegram -- the connection itself failed. "
                      "api.telegram.org is blocked at network level in this region. "
                      "A working proxy, or running this on a cloud server, resolves it.")
        else:
            state = "failing"
            reason = last_failure.get("error") or "Last send attempt failed."
    else:
        state, reason = "unknown", "No real send has been attempted yet, so there is nothing to judge from."

    today_start_iso = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    messages_sent_today = storage.count_telegram_messages_since(today_start_iso)

    return {
        "state": state,
        "reason": reason,
        "can_deliver": state == "working",
        "settings": settings,
        "last_success_at": (last_success or {}).get("sent_at"),
        "last_failure_at": (last_failure or {}).get("sent_at"),
        "last_failure_reason": (last_failure or {}).get("error"),
        "proxy_enabled": settings["proxy_enabled"],
        "proxy_configured": settings["proxy_configured"],
        "messages_sent_today": messages_sent_today,
        "channel_connected": bool(settings["channel_id"]) and state not in ("not_configured",),
    }


def delivery_summary(rows):
    """Period totals: how many signals were generated, how many actually
    reached Telegram, how many were held back and for what reason, and how
    the corresponding trades actually turned out."""
    counts = {k: 0 for k in STATUS_LABELS}
    outcomes = {"win": 0, "loss": 0, "breakeven": 0, "pending": 0, "unknown": 0}
    for r in rows:
        counts[r["delivery_status"]] += 1
        outcomes[r["outcome"]] += 1
    withheld = (counts["withheld_stale"] + counts["withheld_drift"]
                + counts["withheld_switch"] + counts["withheld_rate_limit"])
    failed = counts["blocked_network"] + counts["failed_telegram"] + counts["not_configured"]
    closed = outcomes["win"] + outcomes["loss"] + outcomes["breakeven"]
    return {
        "total_generated": len(rows),
        "delivered": counts["sent"],
        "withheld": withheld,
        "failed": failed,
        "queued": counts["queued"],
        "never_sent": counts["never_sent"],
        "by_status": [
            {"status": k, "label": STATUS_LABELS[k], "count": v}
            for k, v in counts.items() if v
        ],
        "outcomes": outcomes,
        "closed_trades": closed,
        # Win rate across the trades these signals corresponded to. None
        # rather than 0% when nothing has closed yet -- 0% would read as
        # "every one lost", which is a different and false statement.
        "win_rate_pct": round(outcomes["win"] / closed * 100, 1) if closed else None,
    }
