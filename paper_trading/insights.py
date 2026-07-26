"""Paper Trading Insights -- read-only reporting/analytics layer built on
top of existing paper_positions/paper_decision_log data. Nothing here is
called by the trading loop (paper_trading.engine, signal_generator,
position_manager, risk_manager) and nothing here can open, close, or size a
trade -- nothing here can influence a live trading decision. Every function
degrades gracefully (empty list / None / neutral default) when there isn't
enough data yet, since a freshly-deployed strategy will have little or no
history.
"""

from datetime import datetime, timezone

from data_engine import storage


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------- Group 2

def all_confidence_scores(lookback=20):
    """{strategy_id: avg confidence} for every strategy with recent decision
    history, computed from ONE shared decisions query instead of one query
    per strategy (a 14-strategy page would otherwise be 14x slower for no
    reason). Strategies with no decisions yet simply don't appear -- callers
    should treat a missing key as "not enough data" (None)."""
    decisions = storage.list_paper_decisions(limit=1000)
    by_strategy = {}
    for d in decisions:
        sid = d.get("strategy_id")
        conf = d.get("confidence")
        if sid is None or conf is None:
            continue
        by_strategy.setdefault(sid, []).append(conf)
    return {
        sid: round(sum(vals[:lookback]) / len(vals[:lookback]), 1)
        for sid, vals in by_strategy.items()
    }


_REASON_PHRASES = {
    "ema": "the trend average (EMA)",
    "rsi": "momentum (RSI)",
    "value_area": "the volume value area",
    "fvg": "a fair value gap",
    "liquidity_sweep": "a liquidity sweep",
    "pdh": "the previous day's high",
    "pdl": "the previous day's low",
    "candle_break": "a candle breakout",
    "bos": "a break of structure",
    "choch": "a change of character",
}


def humanize_reason(reason_text):
    """Turn a technical rule string ("price < ema + rsi > 40.0 + rsi < 60.0")
    into a short plain-language sentence for non-technical users. Falls back
    to the raw text untouched if it doesn't recognize the shape -- never
    hides information, only tries to simplify it."""
    if not reason_text:
        return "No reason recorded."
    clauses = [c.strip() for c in reason_text.split("+") if c.strip()]
    if not clauses:
        return reason_text
    parts = []
    for clause in clauses:
        low = clause.lower()
        matched = None
        for key, phrase in _REASON_PHRASES.items():
            if key in low:
                matched = phrase
                break
        if matched and matched not in parts:
            parts.append(matched)
    if not parts:
        return reason_text
    return "Signal based on: " + ", ".join(parts) + "."


def detect_alerts(strategy_stats, streaks=None):
    """Real-Time Alert (strong performance) + Drawdown Alert (losing streak),
    computed fresh from current per-strategy stats. `streaks` should be the
    dict returned by all_streaks() -- pass it in rather than letting this
    recompute per strategy, since the caller (paper_trading.py's
    _compute_analytics) already needs it for display too. New alerts are
    persisted (deduplicated per 30-minute window) so the UI has a short
    history instead of the alert vanishing the instant nobody is looking;
    returns the list of alerts newly raised THIS call."""
    if streaks is None:
        streaks = all_streaks()
    now = _now_iso()
    raised = []
    for s in strategy_stats:
        sid = s.get("strategy_id")
        name = s.get("strategy_name") or sid
        trades = s.get("closed_trades") or 0
        win_rate = s.get("win_rate") or 0.0
        total_pnl = s.get("total_pnl") or 0.0

        if trades >= 5 and win_rate >= 70 and total_pnl > 0:
            if not storage.get_recent_paper_alert("strong_performance", sid, _dedupe_window()):
                msg = f"{name} is performing strongly: {win_rate:.0f}% win rate over {trades} trades."
                storage.create_paper_alert("strong_performance", sid, name, msg, "positive", now)
                raised.append({"alert_type": "strong_performance", "strategy_id": sid,
                                "strategy_name": name, "message": msg, "severity": "positive", "created_at": now})

        streak = streaks.get(sid, {"type": "none", "count": 0})
        if streak["type"] == "loss" and streak["count"] >= 3:
            if not storage.get_recent_paper_alert("drawdown", sid, _dedupe_window()):
                msg = f"{name} has lost {streak['count']} trades in a row -- worth a look."
                storage.create_paper_alert("drawdown", sid, name, msg, "warning", now)
                raised.append({"alert_type": "drawdown", "strategy_id": sid,
                                "strategy_name": name, "message": msg, "severity": "warning", "created_at": now})
    return raised


def _dedupe_window():
    """Alerts for the same strategy+type within this window are treated as
    "already raised" instead of spamming a new one every poll."""
    from datetime import timedelta
    return (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()


# --------------------------------------------------------------- Group 3

def classify_win_loss(position):
    """Plain-language Win/Loss Reason Tag for one closed trade. Rule-based
    on fields already recorded at close time (exit_reason, pnl, market
    state) -- never re-runs strategy logic, purely labels the outcome."""
    if position.get("status") != "closed" or position.get("pnl") is None:
        return None
    pnl = position["pnl"]
    exit_reason = (position.get("exit_reason") or "").lower()
    won = pnl > 0

    if "take_profit" in exit_reason or "tp" == exit_reason:
        return "Win: target hit" if won else "Target hit (small loss on fees/slippage)"
    if "stop_loss" in exit_reason or "sl" == exit_reason:
        return "Loss: stop hit as planned" if not won else "Stop hit (still closed positive)"
    if "reversed" in exit_reason:
        return "Closed: opposite signal appeared" if not won else "Win: closed early on opposite signal"
    if "manual" in exit_reason:
        return "Closed manually by a person"
    if "archived" in exit_reason:
        return "Closed during a data reset (not a real market exit)"
    return "Win: closed in profit" if won else ("Loss: closed at a loss" if pnl < 0 else "Closed break-even")


def _streak_from_trades_newest_first(trades_newest_first):
    if not trades_newest_first:
        return {"type": "none", "count": 0}
    first_win = trades_newest_first[0]["pnl"] > 0
    count = 0
    for t in trades_newest_first:
        is_win = t["pnl"] > 0
        if is_win != first_win:
            break
        count += 1
    return {"type": "win" if first_win else "loss", "count": count}


def compute_streak(strategy_id):
    """Consecutive Win/Loss Streak for ONE strategy. Prefer all_streaks()
    when you need this for more than one strategy (e.g. a comparison table)
    -- it does the same computation with a single shared query instead of
    one query per strategy."""
    trades = storage.list_paper_closed_trades_ordered(strategy_id=strategy_id, limit=1000)
    return _streak_from_trades_newest_first(list(reversed(trades)))


def all_streaks(limit=5000):
    """{strategy_id: {"type", "count"}} for every strategy, computed from
    ONE query instead of one per strategy -- see compute_streak's docstring
    for when to prefer this."""
    trades = storage.list_paper_closed_trades_ordered(limit=limit)  # oldest-first, all strategies
    by_strategy = {}
    for t in trades:
        sid = t.get("strategy_id")
        if sid is None:
            continue
        by_strategy.setdefault(sid, []).append(t)
    return {
        sid: _streak_from_trades_newest_first(list(reversed(rows)))
        for sid, rows in by_strategy.items()
    }


def detect_lesson_candidates(min_sample=5, win_rate_extreme=75):
    """Lesson Candidate Auto-Flagging: scans Coin-Specific Pattern Memory for
    (strategy, symbol, market_state, session) combinations with enough
    trades and a strongly one-sided win rate, and flags them for human
    review. NEVER creates or edits an actual lesson -- only writes to
    paper_lesson_candidates with status='flagged'. Returns the candidates
    written this call."""
    patterns = storage.list_paper_coin_pattern_memory()
    now = _now_iso()
    flagged = []
    for p in patterns:
        if p["trades"] < min_sample:
            continue
        if p["win_rate"] < win_rate_extreme and p["win_rate"] > (100 - win_rate_extreme):
            continue
        strong = "wins" if p["win_rate"] >= win_rate_extreme else "loses"
        desc = (f"{p['strategy_name'] or p['strategy_id']} consistently {strong} on {p['symbol']} "
                f"during {p['market_state']} markets in the {p['session']} session "
                f"({p['win_rate']:.0f}% win rate over {p['trades']} trades).")
        storage.save_paper_lesson_candidate(
            p["strategy_id"], p["strategy_name"], p["symbol"], p["market_state"], p["session"],
            desc, p["trades"], p["win_rate"], p["total_pnl"], now,
        )
        flagged.append(desc)
    return flagged


# --------------------------------------------------------------- Group 4

_READY_RULES = [
    "At least 30 closed Paper Trading trades",
    "Win rate of 55% or higher",
    "No current losing streak of 5+ trades",
    "Passed the Automatic Strategy Safety Check",
    "Walk-Forward Test did not FAIL (PASS or not yet run)",
]


def real_trading_readiness(strategy_id, strategy_stats, safety_passed, walk_forward_status):
    """Paper Trading -> Real Trading Bridge: a fixed, documented rule for
    when a strategy is worth CONSIDERING for real trading. This never moves
    money or flips any live/dry_run switch -- it only returns a verdict +
    the checklist behind it, for a person to act on."""
    trades = strategy_stats.get("closed_trades", 0) if strategy_stats else 0
    win_rate = strategy_stats.get("win_rate", 0.0) if strategy_stats else 0.0
    streak = compute_streak(strategy_id)
    losing_streak_ok = not (streak["type"] == "loss" and streak["count"] >= 5)
    wf_ok = walk_forward_status != "FAIL"

    checks = [
        {"label": _READY_RULES[0], "passed": trades >= 30, "detail": f"{trades} closed trades"},
        {"label": _READY_RULES[1], "passed": win_rate >= 55, "detail": f"{win_rate:.1f}% win rate"},
        {"label": _READY_RULES[2], "passed": losing_streak_ok,
         "detail": f"current streak: {streak['count']} {streak['type']}"},
        {"label": _READY_RULES[3], "passed": bool(safety_passed), "detail": "Safety Check"},
        {"label": _READY_RULES[4], "passed": wf_ok, "detail": walk_forward_status or "not yet run"},
    ]
    ready = all(c["passed"] for c in checks)
    return {"strategy_id": strategy_id, "ready_for_real_trading": ready, "checklist": checks}
