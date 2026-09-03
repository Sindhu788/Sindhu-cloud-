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
from data_engine import config as base_config
from paper_trading import config as pt_config


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def fresh_session_start():
    """The timestamp Paper Trading's data was last archived/reset (see
    scripts/archive_and_reset_paper_trading.py), if any. Every insights
    function below scopes its queries to trades/decisions created at or
    after this point -- paper_positions and paper_decision_log rows from
    before a reset are never deleted (kept for audit), so without this
    filter every function here would silently blend pre-fix legacy trades
    back in with the current, trustworthy session's data. Returns None if
    no reset marker exists yet (nothing to scope to -- use all history)."""
    session = base_config.load_or_seed("paper_trading_session.json", {})
    return session.get("fresh_session_started_at")


# --------------------------------------------------------------- Group 2

def all_confidence_scores(lookback=20):
    """{strategy_id: avg confidence} for every strategy with recent decision
    history, computed from ONE shared decisions query instead of one query
    per strategy (a 14-strategy page would otherwise be 14x slower for no
    reason). Strategies with no decisions yet simply don't appear -- callers
    should treat a missing key as "not enough data" (None)."""
    decisions = storage.list_paper_decisions(limit=1000, since=fresh_session_start())
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
    trades = storage.list_paper_closed_trades_ordered(strategy_id=strategy_id, limit=1000, since=fresh_session_start())
    return _streak_from_trades_newest_first(list(reversed(trades)))


def all_streaks(limit=5000):
    """{strategy_id: {"type", "count"}} for every strategy, computed from
    ONE query instead of one per strategy -- see compute_streak's docstring
    for when to prefer this."""
    trades = storage.list_paper_closed_trades_ordered(limit=limit, since=fresh_session_start())  # oldest-first, all strategies
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
    patterns = storage.list_paper_coin_pattern_memory(since=fresh_session_start())
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


# --------------------------------------------------------------- Risk Analytics (Group 2 #6) +
# --------------------------------------------------------------- Drawdown Protection (Group 2 #4)

def compute_risk_metrics(strategy_id, since=None):
    """Sharpe Ratio, Sortino Ratio, and Max/Current Drawdown %, computed
    from this strategy's own closed-trade equity curve (fresh session
    only, via `since`). Standard, well-known formulas -- nothing
    custom-invented:

    Sharpe Ratio: mean(per-trade return) / stdev(per-trade return) * sqrt(N).
    This is the plain per-trade-sample form of the standard Sharpe formula
    (mean excess return / stdev of returns), NOT annualized to calendar time
    since trades arrive at irregular intervals, not one-per-fixed-period --
    annualizing would silently misrepresent an unevenly-spaced trade
    sequence as if it were a regular daily/monthly return series. A
    risk-free rate of 0 is used (paper trading has no risk-free alternative
    to compare against).

    Sortino Ratio (Grand Feature Expansion, Phase 3 Feature 6): the same
    idea as Sharpe, but only penalizes downside variance -- a strategy with
    big WINS and a stable-or-small-loss profile scores higher here than on
    Sharpe, which is exactly the point (upside volatility isn't risk).
    Downside deviation uses the standard population form (divide by N, not
    Sharpe's sample N-1) against a 0 target, per the textbook Sortino
    definition -- target=0 matches this codebase's Sharpe convention above
    (no risk-free alternative in paper trading).

    Max Drawdown %: largest peak-to-trough decline in the cumulative equity
    curve (running balance = initial_balance + cumulative pnl), the
    standard definition used industry-wide.

    Returns None fields (not zeros) when there's too little data to mean
    anything -- degrades gracefully instead of showing a misleading 0.00
    Sharpe for a strategy with one or two trades."""
    trades = storage.list_paper_closed_trades_ordered(strategy_id=strategy_id, limit=2000, since=since)
    if len(trades) < 2:
        return {"sharpe_ratio": None, "sortino_ratio": None, "max_drawdown_pct": None,
                "current_drawdown_pct": None, "sample_size": len(trades)}

    pnls = [t["pnl"] for t in trades if t["pnl"] is not None]
    n = len(pnls)
    if n < 2:
        return {"sharpe_ratio": None, "sortino_ratio": None, "max_drawdown_pct": None,
                "current_drawdown_pct": None, "sample_size": n}

    mean_pnl = sum(pnls) / n
    variance = sum((p - mean_pnl) ** 2 for p in pnls) / (n - 1)  # sample stdev, standard for a finite trade sample
    stdev = variance ** 0.5
    sharpe = round((mean_pnl / stdev) * (n ** 0.5), 3) if stdev > 0 else None

    downside_variance = sum(min(0.0, p) ** 2 for p in pnls) / n
    downside_dev = downside_variance ** 0.5
    # No losing trade at all (downside_dev == 0) means Sortino is undefined
    # (division by zero), not infinite -- reported as None, same "not
    # enough information yet" convention as every other gated metric here.
    sortino = round((mean_pnl / downside_dev) * (n ** 0.5), 3) if downside_dev > 0 else None

    equity = []
    running = 0.0
    for p in pnls:
        running += p
        equity.append(running)

    peak = equity[0]
    max_dd_pct = 0.0
    settings = pt_config.load()
    initial_balance = settings.get("initial_balance", 10000.0)
    for e in equity:
        balance = initial_balance + e
        peak_balance = initial_balance + peak
        if e > peak:
            peak = e
        dd_pct = ((peak_balance - balance) / peak_balance * 100) if peak_balance > 0 else 0.0
        max_dd_pct = max(max_dd_pct, dd_pct)

    current_balance = initial_balance + equity[-1]
    peak_balance = initial_balance + peak
    current_dd_pct = ((peak_balance - current_balance) / peak_balance * 100) if peak_balance > 0 else 0.0

    return {
        "sharpe_ratio": sharpe, "sortino_ratio": sortino, "max_drawdown_pct": round(max_dd_pct, 2),
        "current_drawdown_pct": round(current_dd_pct, 2), "sample_size": n,
    }


def compute_value_at_risk(strategy_id, confidence=0.95, since=None):
    """Grand Feature Expansion, Phase 3 Feature 7: Historical VaR -- "how
    bad could a single trade's loss realistically get" at the given
    confidence level, read directly from this strategy's REAL closed-trade
    PnL distribution (no assumed bell-curve/parametric model, which would
    misrepresent a trading return distribution that is rarely normal).

    Historical simulation method (the standard, simplest VaR approach):
    sort every closed trade's PnL ascending, and the VaR is the loss at
    the (1-confidence) percentile -- e.g. at 95% confidence, 95% of past
    trades lost less than this amount (only the worst 5% were worse).
    Reported as a positive number (a loss magnitude), 0.0 if the worst
    move in the sample was actually still a profit.

    Gated at pattern_stats.MIN_SAMPLE_SIZE (25) -- the same statistical
    floor used everywhere else in this codebase for a real percentile
    estimate, since a handful of trades can't support one honestly."""
    from paper_trading import pattern_stats
    trades = storage.list_paper_closed_trades_ordered(strategy_id=strategy_id, limit=2000, since=since)
    pnls = sorted(t["pnl"] for t in trades if t["pnl"] is not None)
    n = len(pnls)
    if n < pattern_stats.MIN_SAMPLE_SIZE:
        return {"var_amount": None, "var_pct_of_trades_worse": round((1 - confidence) * 100, 1),
                "sample_size": n, "min_sample_size": pattern_stats.MIN_SAMPLE_SIZE}

    index = min(n - 1, int(round((1 - confidence) * n)))
    worst_case_pnl = pnls[index]
    var_amount = round(max(0.0, -worst_case_pnl), 2)
    return {
        "var_amount": var_amount, "var_pct_of_trades_worse": round((1 - confidence) * 100, 1),
        "confidence": confidence, "sample_size": n, "min_sample_size": pattern_stats.MIN_SAMPLE_SIZE,
    }


def compute_mae_mfe_stats(strategy_id, since=None):
    """Grand Feature Expansion, Phase 3 Feature 8: aggregate MAE/MFE across
    a strategy's closed trades -- split by winners vs losers, since the
    genuinely useful question is usually "how much unrealized heat do
    winning trades typically take before working out" (informs whether a
    stop-loss is placed too tight) and "how far did losers run in profit
    before reversing" (informs whether a take-profit is too greedy), not
    one number blending very different trade outcomes together."""
    positions = storage.list_closed_paper_positions(limit=2000, strategy_id=strategy_id, since_iso=since)
    positions = [p for p in positions if p.get("mae_amount") is not None]
    if not positions:
        return {"sample_size": 0, "winners": None, "losers": None}

    winners = [p for p in positions if p.get("is_win")]
    losers = [p for p in positions if p.get("is_win") is False]

    def _avg(rows, key):
        return round(sum(r[key] for r in rows) / len(rows), 2) if rows else None

    return {
        "sample_size": len(positions),
        "winners": {
            "count": len(winners),
            "avg_mae": _avg(winners, "mae_amount"),
            "avg_mfe": _avg(winners, "mfe_amount"),
        } if winners else None,
        "losers": {
            "count": len(losers),
            "avg_mae": _avg(losers, "mae_amount"),
            "avg_mfe": _avg(losers, "mfe_amount"),
        } if losers else None,
    }


def compute_strategy_health_score(strategy_id, since=None):
    """Grand Feature Expansion, Phase 3 Feature 2: Strategy Health Score --
    a single 0-100 composite from win rate, profit factor, drawdown,
    consistency (Sharpe), and sample size. A plain weighted sum of fixed,
    documented thresholds -- no hidden model, no ML -- and every component
    is returned alongside the total so a person can see exactly why a
    strategy scored what it did, not just trust one opaque number.

    Weights (sum to 100): Win Rate 30, Profit Factor 30, Max Drawdown 20,
    Consistency (Sharpe) 10, Sample Size 10. Win Rate and Profit Factor get
    the most weight because they most directly answer "does this actually
    make money"; Drawdown next because it answers "how painful was the
    ride"; Sharpe and Sample Size are smaller trust/confidence adjustments
    on top of those.

    Returns None fields throughout (not a misleading score) when there are
    zero closed trades at all."""
    trades = storage.list_paper_closed_trades_ordered(strategy_id=strategy_id, limit=2000, since=since)
    pnls = [t["pnl"] for t in trades if t["pnl"] is not None]
    n = len(pnls)
    if n == 0:
        return {"health_score": None, "components": None, "sample_size": 0}

    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    win_rate = len(wins) / n * 100

    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    # No losing trade yet -> profit factor is technically infinite, not an
    # honest number to score -- treated as the best possible component
    # score (30) rather than fabricating a finite number, same "don't
    # invent a number you don't have" convention used elsewhere (e.g.
    # challenge_analysis.py's own profit_factor=None for this exact case).
    if gross_loss > 0:
        profit_factor = gross_win / gross_loss
        pf_score = min(30.0, max(0.0, profit_factor / 2.0 * 30.0))  # PF 2.0+ = full marks, PF 1.0 = half marks
    else:
        profit_factor = None
        pf_score = 30.0

    risk = compute_risk_metrics(strategy_id, since=since)
    max_dd = risk.get("max_drawdown_pct")
    # No drawdown data yet (fewer than 2 trades inside compute_risk_metrics'
    # own gate) is treated as neutral (half marks), not a penalty for a
    # strategy that simply hasn't traded enough for that metric yet.
    dd_score = 10.0 if max_dd is None else min(20.0, max(0.0, (1 - min(max_dd, 50.0) / 50.0) * 20.0))
    sharpe = risk.get("sharpe_ratio")
    sharpe_score = 5.0 if sharpe is None else min(10.0, max(0.0, sharpe / 2.0 * 10.0))

    from paper_trading import pattern_stats
    sample_score = min(10.0, n / pattern_stats.MIN_SAMPLE_SIZE * 10.0)

    win_rate_score = min(30.0, win_rate / 100.0 * 30.0)
    total = round(win_rate_score + pf_score + dd_score + sharpe_score + sample_score, 1)

    return {
        "health_score": total,
        "components": {
            "win_rate_score": round(win_rate_score, 1), "win_rate_pct": round(win_rate, 1),
            "profit_factor_score": round(pf_score, 1), "profit_factor": round(profit_factor, 2) if profit_factor is not None else None,
            "drawdown_score": round(dd_score, 1), "max_drawdown_pct": max_dd,
            "consistency_score": round(sharpe_score, 1), "sharpe_ratio": sharpe,
            "sample_size_score": round(sample_score, 1),
        },
        "sample_size": n,
    }


# Grand Feature Expansion, Phase 3 Feature 11: Win-Rate Decay Detection --
# a standalone, always-on version of the same drift math
# paper_trading.challenge_analysis.check_drift() already uses (same
# DRIFT_WIN_RATE_DROP_PTS=15pt threshold, same 15-trade recent window --
# imported, not re-invented), but comparing against this strategy's OWN
# historical baseline (everything before the recent window) instead of a
# Challenge Mode combo's recorded start-of-challenge baseline, so it works
# for every strategy, active challenge or not.
WIN_RATE_DECAY_BASELINE_MIN_SIZE = 25  # same statistical floor as pattern_stats.MIN_SAMPLE_SIZE


def detect_win_rate_decay(strategy_id):
    """Splits this strategy's own closed-trade history into an older
    "baseline" portion and the most recent DRIFT_RECENT_TRADES_WINDOW
    trades, and checks whether the recent win rate has dropped at least
    DRIFT_WIN_RATE_DROP_PTS points below the baseline. Returns
    {"checked": bool, "drifted": bool|None, ...} -- "checked" is False
    (never a guess) when there isn't yet enough history on BOTH sides to
    judge honestly."""
    from paper_trading.challenge_analysis import DRIFT_RECENT_TRADES_WINDOW, DRIFT_WIN_RATE_DROP_PTS

    trades = storage.list_paper_closed_trades_ordered(strategy_id=strategy_id, limit=2000)
    if len(trades) < WIN_RATE_DECAY_BASELINE_MIN_SIZE + DRIFT_RECENT_TRADES_WINDOW:
        return {"checked": False, "drifted": None,
                "reason": f"only {len(trades)} closed trades -- needs at least "
                          f"{WIN_RATE_DECAY_BASELINE_MIN_SIZE + DRIFT_RECENT_TRADES_WINDOW} "
                          f"(a real baseline plus a real recent window) to judge decay honestly"}

    recent = trades[-DRIFT_RECENT_TRADES_WINDOW:]
    baseline = trades[:-DRIFT_RECENT_TRADES_WINDOW]

    baseline_win_rate = sum(1 for t in baseline if t["pnl"] > 0) / len(baseline) * 100
    recent_win_rate = sum(1 for t in recent if t["pnl"] > 0) / len(recent) * 100
    drop = baseline_win_rate - recent_win_rate
    drifted = drop >= DRIFT_WIN_RATE_DROP_PTS

    return {
        "checked": True, "drifted": drifted,
        "baseline_win_rate_pct": round(baseline_win_rate, 1), "baseline_sample_size": len(baseline),
        "recent_win_rate_pct": round(recent_win_rate, 1), "recent_sample_size": len(recent),
        "win_rate_drop_pts": round(drop, 1),
    }


WIN_RATE_DECAY_ALERT_RECHECK_HOURS = 24


def sweep_win_rate_decay_alerts():
    """Checks every known strategy and raises ONE paper_alerts entry the
    first time (per WIN_RATE_DECAY_ALERT_RECHECK_HOURS) it's found to have
    decayed -- same throttle-and-alert shape as
    signal_tracker.check_and_alert_divergence, reusing the existing
    paper_alerts table/Alerts dashboard section rather than a new
    notification channel."""
    from datetime import datetime, timedelta, timezone
    from backtest_engine import strategy_library as lib

    now_iso = datetime.now(timezone.utc).isoformat()
    since = (datetime.now(timezone.utc) - timedelta(hours=WIN_RATE_DECAY_ALERT_RECHECK_HOURS)).isoformat()

    alerted = []
    for meta in lib.list_all():
        sid = meta["id"]
        result = detect_win_rate_decay(sid)
        if not result["checked"] or not result["drifted"]:
            continue
        if storage.get_recent_paper_alert("win_rate_decay", sid, since):
            continue
        message = (
            f"{meta['name']}: win rate dropped from {result['baseline_win_rate_pct']}% "
            f"(baseline, {result['baseline_sample_size']} trades) to {result['recent_win_rate_pct']}% "
            f"(last {result['recent_sample_size']} trades) -- a {result['win_rate_drop_pts']} point drop. "
            f"Worth reviewing whether market conditions have changed for this strategy."
        )
        storage.create_paper_alert("win_rate_decay", sid, meta["name"], message, "warning", now_iso)
        alerted.append(sid)
    return alerted


def compute_strategy_aging(strategy_id, window_size=10):
    """Grand Feature Expansion, Phase 3 Feature 12: Strategy Aging
    Analysis -- a TREND-over-time view, distinct from every other metric
    in this module (all of which are a single current-state snapshot).
    Splits closed trades (oldest first) into consecutive windows of
    `window_size` trades each and reports each window's win rate/PnL, plus
    a simple, transparent trend verdict comparing the average win rate of
    the OLDEST half of windows against the NEWEST half -- no curve-fitting
    or hidden model, just "is the second half of this strategy's life
    doing better or worse than the first half."

    Needs at least 3 full windows (30 trades by default) to report a real
    trend -- fewer than that returns windows=[] with an honest reason
    rather than a trend verdict built on 1-2 data points."""
    trades = storage.list_paper_closed_trades_ordered(strategy_id=strategy_id, limit=2000)
    n_windows = len(trades) // window_size
    if n_windows < 3:
        return {"windows": [], "trend": None,
                "reason": f"only {len(trades)} closed trades ({n_windows} full window(s) of {window_size}) -- "
                          f"needs at least 3 full windows to show a real trend"}

    windows = []
    for i in range(n_windows):
        chunk = trades[i * window_size:(i + 1) * window_size]
        wins = sum(1 for t in chunk if t["pnl"] > 0)
        windows.append({
            "window_index": i, "trade_count": len(chunk),
            "win_rate_pct": round(wins / len(chunk) * 100, 1),
            "total_pnl": round(sum(t["pnl"] for t in chunk), 2),
            "period_start": chunk[0].get("closed_at"), "period_end": chunk[-1].get("closed_at"),
        })

    half = n_windows // 2
    older_avg_win_rate = sum(w["win_rate_pct"] for w in windows[:half]) / half
    newer_avg_win_rate = sum(w["win_rate_pct"] for w in windows[-half:]) / half
    change_pts = round(newer_avg_win_rate - older_avg_win_rate, 1)

    if change_pts >= 10:
        trend = "improving"
    elif change_pts <= -10:
        trend = "weakening"
    else:
        trend = "stable"

    return {
        "windows": windows, "window_size": window_size, "trend": trend,
        "older_half_avg_win_rate_pct": round(older_avg_win_rate, 1),
        "newer_half_avg_win_rate_pct": round(newer_avg_win_rate, 1),
        "win_rate_change_pts": change_pts,
    }


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
