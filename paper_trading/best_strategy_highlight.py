"""Grand Master Batch, Phase 4 Item 13: "Best Strategy This Month" auto-
highlight for the main Dashboard -- distinct from paper_trading/
telegram_analytics.py's best_performing_strategy(), which is scoped only
to Telegram-signaled trades and requires picking a period from a
dropdown. This one covers every real paper-trading trade (Telegram-sent
or not) and is always "this calendar month", computed fresh on load, not
something the CEO has to go select.
"""

from datetime import datetime, timezone

from data_engine import storage


def _strategy_names():
    try:
        from backtest_engine import strategy_library as lib
        return {m["id"]: m["name"] for m in lib.list_all()}
    except Exception:
        return {}


def best_strategy_this_month(now=None):
    """The strategy with the highest real realized PnL among trades
    CLOSED so far this calendar month (UTC) -- None if nothing has closed
    yet this month. Only ever a real, already-recorded result; never a
    projection or an average."""
    now = now or datetime.now(timezone.utc)
    month_start_iso = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    closed = storage.list_closed_paper_positions(limit=100000, since_iso=month_start_iso)
    if not closed:
        return None
    totals = {}
    wins = {}
    counts = {}
    for pos in closed:
        sid = pos.get("strategy_id") or "__lessons__"
        pnl = pos.get("pnl") or 0.0
        totals[sid] = totals.get(sid, 0.0) + pnl
        counts[sid] = counts.get(sid, 0) + 1
        if pnl > 0:
            wins[sid] = wins.get(sid, 0) + 1
    best_sid = max(totals, key=lambda sid: totals[sid])
    names = _strategy_names()
    return {
        "strategy_id": None if best_sid == "__lessons__" else best_sid,
        "strategy_name": names.get(best_sid, best_sid) if best_sid != "__lessons__" else "Lesson-only signals",
        "total_pnl": round(totals[best_sid], 2),
        "closed_trades": counts[best_sid],
        "win_rate_pct": round(wins.get(best_sid, 0) / counts[best_sid] * 100, 1),
        "month": now.strftime("%Y-%m"),
    }
