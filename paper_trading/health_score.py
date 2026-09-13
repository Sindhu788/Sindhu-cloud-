"""Grand Master Batch, Phase 3: System Health Score.

One 0-100 number combining four already-real signals into a single
glanceable indicator for the top of the dashboard -- distinct from
paper_trading.health_check's infrastructure self-test (database
connection, engine state, live candle fetch). This one is about trading
health, not process health: nothing here computes a new trading signal
or influences trading behavior, it only reads state that already exists
elsewhere and combines it.

Each component is scored 0-100 on its own (with its own real detail
string), then combined by a documented weighted average -- the exact
"Show Me the Math" combined-scoring logic is the WEIGHTS dict below plus
each component's own score, both returned in full by compute() so the
dashboard (or a future "Show Me the Math" button) can display exactly
how the number was reached rather than a black box.
"""

from datetime import datetime, timedelta, timezone

from data_engine import storage
from paper_trading import account_drawdown_guard, kill_switch, telegram_delivery

WEIGHTS = {
    "profitable_ratio": 0.30,
    "telegram_delivery": 0.20,
    "safety_gates": 0.30,
    "pnl_trend": 0.20,
}

_TELEGRAM_STATE_SCORE = {
    "working": 100,
    # Off/unconfigured is a deliberate CEO choice, not a failure -- scored
    # neutral rather than penalized the same as a real delivery failure.
    "turned_off": 50,
    "not_configured": 50,
    "unknown": 50,
    "blocked": 0,
    "failing": 0,
}

_PNL_TREND_WINDOW_DAYS = 7


def _profitable_ratio_component():
    """% of strategies real enough to have been classified into a group
    (paper_trading.strategy_groups) that are currently in the Profitable
    group. A strategy with no group yet (too new to classify) is excluded
    from the denominator -- it hasn't earned a verdict either way."""
    assignments = storage.list_paper_strategy_groups()
    if not assignments:
        return {
            "score": 50, "profitable_count": 0, "classified_count": 0,
            "detail": "no strategy has been classified into a group yet",
        }
    profitable_count = sum(1 for g in assignments.values() if g == "profitable")
    classified_count = len(assignments)
    pct = profitable_count / classified_count * 100
    return {
        "score": round(pct, 1), "profitable_count": profitable_count, "classified_count": classified_count,
        "detail": f"{profitable_count}/{classified_count} classified strategies are in the Profitable group",
    }


def _telegram_component():
    """Reuses the exact same real state the Telegram dashboard's own
    connection-status card shows (paper_trading.telegram_delivery.
    connection_status) -- never a second, separately-computed opinion."""
    status = telegram_delivery.connection_status()
    state = status["state"]
    return {"score": _TELEGRAM_STATE_SCORE.get(state, 50), "state": state, "detail": status["reason"]}


def _safety_gate_component():
    """Any currently-tripped safety gate (Kill Switch, account-wide
    Drawdown Protection pause, or any individual strategy paused by
    Drawdown Protection) drives this component straight to 0 -- a tripped
    gate is a real, serious signal that should not be diluted by getting
    averaged against a merely-mediocre score elsewhere."""
    tripped = []
    if kill_switch.is_active():
        tripped.append("kill switch is active")
    if account_drawdown_guard.is_globally_paused():
        tripped.append("account-wide Drawdown Protection pause is active")
    paused_strategies = storage.list_paused_strategies()
    if paused_strategies:
        tripped.append(f"{len(paused_strategies)} strategy(ies) paused by Drawdown Protection")
    if tripped:
        return {"score": 0, "tripped": tripped, "detail": "Tripped: " + "; ".join(tripped)}
    return {"score": 100, "tripped": [], "detail": "No safety gate is currently tripped"}


def _pnl_trend_component():
    """Real realized PnL summed across every position actually closed in
    the last _PNL_TREND_WINDOW_DAYS days -- positive scores well, negative
    scores poorly, exactly flat/zero (or nothing closed yet to judge) is
    neutral. Uses paper_positions directly (storage.list_closed_paper_
    positions), the same source of truth every other real PnL figure in
    the app already reads from."""
    now = datetime.now(timezone.utc)
    since_iso = (now - timedelta(days=_PNL_TREND_WINDOW_DAYS)).isoformat()
    recent = storage.list_closed_paper_positions(limit=100000, since_iso=since_iso)
    if not recent:
        return {
            "score": 50, "recent_pnl": 0.0, "recent_trade_count": 0,
            "detail": f"no trades closed in the last {_PNL_TREND_WINDOW_DAYS} days to judge a trend from",
        }
    recent_pnl = sum(p.get("pnl") or 0.0 for p in recent)
    score = 100 if recent_pnl > 0 else 50 if recent_pnl == 0 else 0
    return {
        "score": score, "recent_pnl": round(recent_pnl, 2), "recent_trade_count": len(recent),
        "detail": f"${recent_pnl:.2f} real realized PnL across {len(recent)} trades closed in the last {_PNL_TREND_WINDOW_DAYS} days",
    }


def _color_for(score):
    if score >= 75:
        return "green"
    if score >= 50:
        return "yellow"
    return "red"


def compute():
    components = {
        "profitable_ratio": _profitable_ratio_component(),
        "telegram_delivery": _telegram_component(),
        "safety_gates": _safety_gate_component(),
        "pnl_trend": _pnl_trend_component(),
    }
    overall = sum(components[key]["score"] * WEIGHTS[key] for key in WEIGHTS)
    return {
        "score": round(overall),
        "color": _color_for(overall),
        "components": {key: {"weight": WEIGHTS[key], **value} for key, value in components.items()},
    }
