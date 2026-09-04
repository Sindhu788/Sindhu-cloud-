"""Challenge Mode Levels 1 & 2 (full redesign): granular per-strategy,
per-coin, and per-strategy-coin performance breakdown, plus honest,
confidence-graded, consistency-checked recommendations.

This module is READ-ONLY analysis over real closed paper_positions. It
never computes a trade decision, never touches risk_pct/position sizing/
entry conditions, and nothing here is read by the trading engine -- same
boundary paper_trading.challenge_mode already documents for itself.

Fixes the original Challenge Mode's known design flaw: instead of judging
a target against ONE system-wide blended pace (which a weak combination
can drag down even while a specific strategy+coin pairing is genuinely
strong), every number here is computed per REAL strategy-coin combination
from its own trade history.
"""

import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from data_engine import storage
from paper_trading import config as pt_config, pattern_stats

_MAX_ROWS = 1_000_000  # effectively "all of history" for list_closed_paper_positions

# A combination's real, demonstrated daily pace must clear the actual
# required pace to be called "achievable at this pace" -- no slack, no
# rounding in the user's favor (matches the project's standing "an
# inconvenient truth beats false comfort" principle).
CONSISTENCY_WINDOW_DAYS = 7
CONSISTENCY_CONCENTRATION_THRESHOLD = 0.60  # >=60% of positive PnL from one window = flag it
DRIFT_WIN_RATE_DROP_PTS = 15.0
DRIFT_RECENT_TRADES_WINDOW = 15


def _closed_rows(strategy_id=None, symbol=None):
    rows = storage.list_closed_paper_positions(limit=_MAX_ROWS, strategy_id=strategy_id)
    rows = [r for r in rows if r.get("pnl") is not None and r.get("strategy_id") is not None]
    if symbol:
        rows = [r for r in rows if r["symbol"] == symbol]
    return rows


def _duration_minutes(row):
    if not row.get("entry_time") or not row.get("exit_time"):
        return None
    return (row["exit_time"] - row["entry_time"]) / 60000.0


def _max_drawdown(rows_sorted_by_close):
    """Real equity-curve max drawdown on this combination's own pnl
    sequence (in $, relative to its own running peak) -- not tied to any
    particular account balance."""
    peak = 0.0
    equity = 0.0
    max_dd = 0.0
    for r in rows_sorted_by_close:
        equity += r["pnl"]
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return max_dd


def _metrics_for(rows):
    n = len(rows)
    if n == 0:
        return None
    wins = [r for r in rows if r["pnl"] > 0]
    losses = [r for r in rows if r["pnl"] < 0]
    total_pnl = sum(r["pnl"] for r in rows)
    gross_win = sum(r["pnl"] for r in wins)
    gross_loss = abs(sum(r["pnl"] for r in losses))
    if gross_loss > 0:
        profit_factor = round(gross_win / gross_loss, 2)
    elif gross_win > 0:
        profit_factor = None  # no losing trades yet -- an "infinite" profit factor is not an honest number to show
    else:
        profit_factor = None
    durations = [d for d in (_duration_minutes(r) for r in rows) if d is not None]
    rows_sorted = sorted(rows, key=lambda r: r.get("closed_at") or "")
    return {
        "total_closed_trades": n,
        "win_count": len(wins),
        "win_rate_pct": round(len(wins) / n * 100, 2),
        "avg_return_per_trade": round(total_pnl / n, 4),
        "profit_factor": profit_factor,
        "max_drawdown": round(_max_drawdown(rows_sorted), 2),
        "avg_trade_duration_minutes": round(sum(durations) / len(durations), 1) if durations else None,
        "total_pnl": round(total_pnl, 2),
    }


# --------------------------------------------------------------- Level 1: granular breakdown

def granular_breakdown():
    """Real per-strategy, per-coin, and per-strategy-coin performance,
    computed entirely from stored closed trades -- never estimated or
    extrapolated. Returns {"by_strategy", "by_coin", "by_combination"}
    (each sorted by total_pnl desc), "best_combination", and
    "top_combinations" (top 5)."""
    rows = _closed_rows()
    by_strategy_rows = defaultdict(list)
    by_coin_rows = defaultdict(list)
    by_combo_rows = defaultdict(list)
    names = {}
    for r in rows:
        sid = r["strategy_id"]
        names[sid] = r.get("strategy_name") or sid
        by_strategy_rows[sid].append(r)
        by_coin_rows[r["symbol"]].append(r)
        by_combo_rows[(sid, r["symbol"])].append(r)

    def _build(grouped, key_fn):
        out = []
        for key, group_rows in grouped.items():
            m = _metrics_for(group_rows)
            if m:
                out.append({**key_fn(key), **m})
        out.sort(key=lambda x: x["total_pnl"], reverse=True)
        return out

    by_strategy = _build(by_strategy_rows, lambda sid: {"strategy_id": sid, "strategy_name": names.get(sid, sid)})
    by_coin = _build(by_coin_rows, lambda sym: {"symbol": sym})
    by_combination = _build(
        by_combo_rows,
        lambda k: {"strategy_id": k[0], "strategy_name": names.get(k[0], k[0]), "symbol": k[1]},
    )

    return {
        "by_strategy": by_strategy, "by_coin": by_coin, "by_combination": by_combination,
        "best_combination": by_combination[0] if by_combination else None,
        "top_combinations": by_combination[:5],
    }


# --------------------------------------------------------------- Best Combination Auto-Suggest (multi-strategy)
# Grand Feature Expansion, Phase 5 Feature 11: the existing
# granular_breakdown() above already auto-suggests the single best
# strategy+coin PAIRING -- this extends it to a genuine multi-strategy
# PORTFOLIO suggestion. Still read-only analysis (this module's own
# module docstring: "nothing here is read by the trading engine"),
# purely informational -- a human applies the idea via each strategy's
# own existing enable/pause controls, nothing here activates anything.

def suggest_best_portfolio(top_n=3):
    """Top `top_n` DISTINCT strategies' best coin each, ranked by real PnL,
    filtered to combinations with enough trades to statistically trust
    (pattern_stats.MIN_SAMPLE_SIZE) -- never suggests the same strategy
    twice (running one strategy several times isn't a diversified
    portfolio), and never fabricates a suggestion when nothing has enough
    real history yet."""
    breakdown = granular_breakdown()
    trusted = [c for c in breakdown["by_combination"] if c["total_closed_trades"] >= pattern_stats.MIN_SAMPLE_SIZE]

    portfolio = []
    seen_strategies = set()
    for c in trusted:
        if c["strategy_id"] in seen_strategies:
            continue
        seen_strategies.add(c["strategy_id"])
        portfolio.append(c)
        if len(portfolio) >= top_n:
            break

    combined_pnl = round(sum(c["total_pnl"] for c in portfolio), 2)
    reason = (
        f"Top {len(portfolio)} distinct, statistically-trusted strategy+coin combination(s) by real PnL "
        f"(each with {pattern_stats.MIN_SAMPLE_SIZE}+ closed trades), one coin per strategy."
        if portfolio else
        f"No strategy+coin combination has reached {pattern_stats.MIN_SAMPLE_SIZE} closed trades yet -- "
        f"nothing statistically trustworthy to suggest as a portfolio."
    )
    return {"portfolio": portfolio, "combined_pnl": combined_pnl, "reason": reason}


# --------------------------------------------------------------- Level 2: consistency check

def consistency_check(strategy_id, symbol, window_days=CONSISTENCY_WINDOW_DAYS):
    """Breaks this combination's closed-trade history into window_days
    chronological buckets and flags whether its positive PnL is actually
    concentrated in one unusually good window rather than sustained
    across its whole history. Never guesses with fewer than
    pattern_stats.MIN_SAMPLE_SIZE trades (nothing statistically meaningful
    to check yet), or with only a single time window (nothing to compare
    against)."""
    rows = [r for r in _closed_rows(strategy_id, symbol) if r.get("closed_at")]
    if len(rows) < pattern_stats.MIN_SAMPLE_SIZE:
        return {"checked": False, "concentrated": None,
                "reason": f"only {len(rows)} closed trades so far -- need {pattern_stats.MIN_SAMPLE_SIZE} "
                          f"before a consistency check means anything"}

    rows.sort(key=lambda r: r["closed_at"])
    first = datetime.fromisoformat(rows[0]["closed_at"])
    buckets = defaultdict(float)
    for r in rows:
        closed = datetime.fromisoformat(r["closed_at"])
        idx = int((closed - first).total_seconds() // (window_days * 86400))
        buckets[idx] += r["pnl"]

    if len(buckets) < 2:
        return {"checked": False, "concentrated": None, "windows": len(buckets),
                "reason": "all trades fall inside a single time window so far -- too short a history to "
                          "check for concentration yet"}

    positive_total = sum(v for v in buckets.values() if v > 0)
    best_window_pnl = max(buckets.values())
    if positive_total <= 0:
        return {"checked": True, "concentrated": False, "windows": len(buckets),
                "note": "no net-positive window at all -- nothing to be misleadingly concentrated in"}

    share = best_window_pnl / positive_total
    concentrated = share >= CONSISTENCY_CONCENTRATION_THRESHOLD
    return {
        "checked": True, "windows": len(buckets), "window_days": window_days,
        "best_window_pnl": round(best_window_pnl, 2),
        "share_of_positive_pnl_in_best_window_pct": round(share * 100, 1),
        "concentrated": concentrated,
        "note": (
            f"{share*100:.0f}% of this combination's positive PnL came from a single {window_days}-day "
            f"window -- this could be a one-off good stretch rather than sustained performance."
            if concentrated else
            "Performance is spread across multiple time windows, not concentrated in one lucky stretch."
        ),
    }


def _required_daily_rate(start_amount, target_amount, days):
    if start_amount <= 0 or days <= 0 or target_amount <= start_amount:
        return 0.0
    return (target_amount / start_amount) ** (1.0 / days) - 1.0


def _combo_daily_rate(strategy_id, symbol, rows=None):
    """This exact combination's own real demonstrated daily compound
    growth rate: its own average R-multiple * the configured risk % *
    its own real trade frequency -- never the system-wide blended number.
    Returns (daily_rate, avg_r_multiple, trades_per_day) or (None, None,
    None) if there's no usable risk-sized history yet."""
    rows = rows if rows is not None else _closed_rows(strategy_id, symbol)
    valid = [r for r in rows if r.get("risk_amount")]
    if not valid:
        return None, None, None
    avg_r_multiple = sum(r["pnl"] / r["risk_amount"] for r in valid) / len(valid)
    closed_dates = [r["closed_at"] for r in rows if r.get("closed_at")]
    if not closed_dates:
        return None, None, None
    first_closed = min(closed_dates)
    elapsed_days = max(1.0, (datetime.now(timezone.utc) - datetime.fromisoformat(first_closed)).total_seconds() / 86400)
    trades_per_day = len(rows) / elapsed_days
    risk_pct = pt_config.load().get("risk_pct_default", 1.0) / 100.0
    daily_rate = avg_r_multiple * risk_pct * trades_per_day
    return daily_rate, avg_r_multiple, trades_per_day


def recommend_paths(start_amount, target_amount, days, restrict_symbols=None, restrict_strategy_ids=None):
    """Level 2's main output: multiple honest, ranked viable paths toward
    a target, each derived from ONE real strategy-coin combination's own
    demonstrated performance -- never an invented "risk profile". Each
    path carries a Wilson-gated confidence label and a consistency-check
    verdict, and explicitly states its sample size.

    restrict_symbols / restrict_strategy_ids: optional filters for the
    What-If explorer (Level 3) -- when given, only combinations matching
    are considered, but every number is still computed fresh from real
    history, never cached or extrapolated from the unfiltered view.

    Returns {"paths": [...top 5...], "any_achievable": bool,
             "fallback": {...} | None, "required_daily_rate_pct": float}."""
    breakdown = granular_breakdown()
    combos = breakdown["by_combination"]
    if restrict_symbols:
        combos = [c for c in combos if c["symbol"] in restrict_symbols]
    if restrict_strategy_ids:
        combos = [c for c in combos if c["strategy_id"] in restrict_strategy_ids]

    required_daily_rate = _required_daily_rate(start_amount, target_amount, days)
    paths = []
    for combo in combos:
        sid, sym, n = combo["strategy_id"], combo["symbol"], combo["total_closed_trades"]
        combo_rows = _closed_rows(sid, sym)
        daily_rate, avg_r_multiple, trades_per_day = _combo_daily_rate(sid, sym, combo_rows)
        if daily_rate is None:
            continue

        conf = pattern_stats.classify(combo["win_count"], n)
        consistency = consistency_check(sid, sym)
        achievable = daily_rate > 0 and required_daily_rate <= daily_rate
        projected_days = None
        if daily_rate > 0 and target_amount > start_amount:
            projected_days = math.log(target_amount / start_amount) / math.log(1 + daily_rate)

        paths.append({
            "strategy_id": sid, "strategy_name": combo["strategy_name"], "symbol": sym,
            "sample_size": n, "win_rate_pct": combo["win_rate_pct"],
            "profit_factor": combo["profit_factor"], "max_drawdown": combo["max_drawdown"],
            "avg_trade_duration_minutes": combo["avg_trade_duration_minutes"],
            "avg_r_multiple": round(avg_r_multiple, 3) if avg_r_multiple is not None else None,
            "trades_per_day": round(trades_per_day, 3) if trades_per_day is not None else None,
            "demonstrated_daily_rate_pct": round(daily_rate * 100, 4),
            "achievable_at_this_pace": achievable,
            "projected_days_to_target": round(projected_days, 1) if projected_days else None,
            "confidence": conf,
            "consistency": consistency,
            "profile": "faster pace, more frequent trades" if (trades_per_day or 0) >= 0.5
                       else "steadier pace, needs more time to accumulate trades",
        })

    paths.sort(key=lambda p: (p["achievable_at_this_pace"], p["demonstrated_daily_rate_pct"]), reverse=True)
    achievable_paths = [p for p in paths if p["achievable_at_this_pace"]]

    fallback = None
    if not achievable_paths and paths:
        best = paths[0]
        if best["demonstrated_daily_rate_pct"] > 0:
            rate = best["demonstrated_daily_rate_pct"] / 100.0
            realistic_amount_in_same_days = start_amount * ((1 + rate) ** days)
            days_needed = math.log(target_amount / start_amount) / math.log(1 + rate) if target_amount > start_amount else None
            fallback = {
                "based_on_strategy_id": best["strategy_id"], "based_on_strategy_name": best["strategy_name"],
                "based_on_symbol": best["symbol"], "based_on_sample_size": best["sample_size"],
                "realistic_amount_in_same_days": round(realistic_amount_in_same_days, 2),
                "days_needed_for_original_target": round(days_needed, 1) if days_needed else None,
            }

    return {
        "paths": paths[:5],
        "any_achievable": bool(achievable_paths),
        "fallback": fallback,
        "required_daily_rate_pct": round(required_daily_rate * 100, 4),
        "combinations_considered": len(paths),
    }


# --------------------------------------------------------------- Level 3: drift detection

def check_drift(strategy_id, symbol, baseline_win_rate_pct, window_trades=DRIFT_RECENT_TRADES_WINDOW):
    """Has this combination's performance materially degraded since a
    challenge was started against it? Compares the most recent
    `window_trades` real closed trades' win rate against the baseline
    win rate recorded when the challenge started. Never silent -- always
    returns a verdict, including an honest "too few recent trades yet"."""
    rows = _closed_rows(strategy_id, symbol)
    rows.sort(key=lambda r: r.get("closed_at") or "")
    recent = rows[-window_trades:]
    if len(recent) < 10:
        return {"checked": False, "drifted": None,
                "reason": f"only {len(recent)} recent closed trades -- too few to judge drift yet"}

    wins = sum(1 for r in recent if r["pnl"] > 0)
    recent_win_rate = wins / len(recent) * 100
    win_rate_drop = baseline_win_rate_pct - recent_win_rate
    drifted = win_rate_drop >= DRIFT_WIN_RATE_DROP_PTS
    return {
        "checked": True, "recent_trades": len(recent),
        "recent_win_rate_pct": round(recent_win_rate, 1),
        "baseline_win_rate_pct": round(baseline_win_rate_pct, 1),
        "win_rate_drop_pts": round(win_rate_drop, 1),
        "drifted": drifted,
        "note": (
            f"Is challenge ka basis combo ka win rate {baseline_win_rate_pct:.0f}% se gir kar "
            f"{recent_win_rate:.0f}% ho gaya hai (pichle {len(recent)} real trades mein) -- yeh plan ke "
            f"asal basis se hat raha hai."
            if drifted else
            "Combo abhi bhi apne original baseline ke qareeb perform kar raha hai -- koi warning nahi."
        ),
    }


# --------------------------------------------------------------- Master Task 3, Phase 2 (Challenge Mode Part 1)
# Everything below reuses recommend_paths()/granular_breakdown()'s already-
# computed real numbers rather than re-querying storage from scratch --
# same "never fabricate, always derive from real stored trades" boundary
# this whole module already documents for itself.

DIFFICULTY_BANDS = [
    (0.5, "Easy"), (1.0, "Moderate"), (2.0, "Hard"),
]  # multiple = required_daily_rate / real_daily_rate; above the last band's ceiling -> "Extremely Unlikely"

# A suggested risk % this many times the CEO's own configured default is
# flagged outright -- pushing risk that much higher to chase a target is a
# materially different (and materially more dangerous) choice than the
# CEO's own standing default, not a small tweak.
RISK_WARNING_MULTIPLE = 2.0
MAX_SANE_RISK_PCT = 5.0  # never suggest risking more than this per trade, full stop


def difficulty_rating(required_daily_rate_pct, real_daily_rate_pct):
    """Phase 2.14: a single plain-language label alongside the detailed
    numbers -- Easy/Moderate/Hard/Extremely Unlikely, derived from the
    exact same required-vs-real-pace multiple challenge_mode.py's own
    UNREALISTIC_MULTIPLE concept already uses, just with finer bands."""
    if real_daily_rate_pct is None or real_daily_rate_pct <= 0:
        return "Extremely Unlikely"
    multiple = required_daily_rate_pct / real_daily_rate_pct
    for ceiling, label in DIFFICULTY_BANDS:
        if multiple <= ceiling:
            return label
    return "Extremely Unlikely"


def best_worst_likely_range(start_amount, target_amount, days, restrict_symbols=None, restrict_strategy_ids=None):
    """Phase 2.11: instead of one single probability estimate, a real
    best-case/likely-case/worst-case range -- each case is one REAL
    strategy+coin combination's own demonstrated pace (the best, median,
    and worst of recommend_paths()'s own candidate list), never an
    invented spread around a single number."""
    result = recommend_paths(start_amount, target_amount, days, restrict_symbols, restrict_strategy_ids)
    paths = result["paths"]
    if not paths:
        return {"best_case": None, "likely_case": None, "worst_case": None,
                "reason": "No real strategy+coin combination has enough history yet."}

    def _case(path):
        rate_pct = path["demonstrated_daily_rate_pct"]
        return {
            "strategy_name": path["strategy_name"], "symbol": path["symbol"],
            "daily_rate_pct": rate_pct, "days_to_target": path["projected_days_to_target"],
            "sample_size": path["sample_size"],
        }

    by_rate = sorted(paths, key=lambda p: p["demonstrated_daily_rate_pct"], reverse=True)
    return {
        "best_case": _case(by_rate[0]),
        "worst_case": _case(by_rate[-1]),
        "likely_case": _case(by_rate[len(by_rate) // 2]),
        "combinations_considered": len(by_rate),
    }


def suggest_adaptive_risk_pct(required_daily_rate_pct, avg_r_multiple, trades_per_day, current_risk_pct):
    """Phase 2.12: the SPECIFIC risk % that would make a real combination's
    own demonstrated edge (avg R-multiple * trade frequency) match the
    required pace -- e.g. '0.75% risk', never a vague 'increase risk'.
    None when the combination has no positive edge at all (no risk % can
    fix a strategy with a non-positive expectancy)."""
    if not avg_r_multiple or avg_r_multiple <= 0 or not trades_per_day:
        return None
    needed_risk_pct = round((required_daily_rate_pct / 100) / (avg_r_multiple * trades_per_day) * 100, 3)
    return {
        "suggested_risk_pct": needed_risk_pct,
        "current_risk_pct": current_risk_pct,
        "increase_multiple": round(needed_risk_pct / current_risk_pct, 2) if current_risk_pct else None,
    }


def risk_level_warning(suggested_risk_pct, current_risk_pct):
    """Phase 2.8: if hitting a target would require pushing risk % well
    beyond the CEO's own configured default (or past a hard sanity
    ceiling), say so plainly instead of silently implying a higher-risk
    path is fine."""
    if suggested_risk_pct is None:
        return None
    warnings = []
    if suggested_risk_pct > MAX_SANE_RISK_PCT:
        warnings.append(
            f"{suggested_risk_pct}% risk per trade is beyond any reasonable ceiling ({MAX_SANE_RISK_PCT}%) -- "
            f"this target should not be chased by raising risk at all."
        )
    elif current_risk_pct and suggested_risk_pct >= current_risk_pct * RISK_WARNING_MULTIPLE:
        warnings.append(
            f"Hitting this target at the demonstrated pace would need {suggested_risk_pct}% risk per trade -- "
            f"{round(suggested_risk_pct / current_risk_pct, 1)}x your current {current_risk_pct}% default. "
            f"That is a materially riskier choice, not a small tweak."
        )
    return {"warn": bool(warnings), "messages": warnings}


def give_up_point_check(remaining_days, best_case_days_to_target):
    """Phase 2.10: an honest 'this is now mathematically implausible in
    the time left' alert -- compares the real BEST demonstrated path's own
    projected days-to-target against how much time is actually left,
    rather than continuing to show a hopeful-looking progress bar."""
    if remaining_days <= 0:
        return {"implausible": True, "reason": "The challenge's deadline has already passed."}
    if best_case_days_to_target is None:
        return {"implausible": True,
                "reason": "No real combination has ever demonstrated a positive pace toward this target."}
    if best_case_days_to_target > remaining_days:
        return {"implausible": True,
                "reason": (
                    f"Even the single BEST real combination available would need {best_case_days_to_target:.1f} "
                    f"more days at its own demonstrated pace, but only {remaining_days:.1f} days remain -- "
                    f"this target is no longer mathematically reachable in time."
                )}
    return {"implausible": False, "reason": None}


def _max_losing_streak(rows_sorted_by_close):
    """Phase 2.19: the REAL worst consecutive-loss run in this
    combination's own history -- mirrors _max_drawdown's same
    equity-sequence-walk shape above, just counting consecutive losses
    instead of dollar drawdown."""
    worst = current = 0
    for r in rows_sorted_by_close:
        if r["pnl"] < 0:
            current += 1
            worst = max(worst, current)
        else:
            current = 0
    return worst


def loss_streak_impact(strategy_id, symbol, start_amount, risk_pct=None):
    """Phase 2.19: what happens to the timeline if this combination's OWN
    real worst-ever losing streak (not an invented number) hit again,
    starting from today -- the dollar cost of that many losses at the
    combination's own average loss size, and how many extra winning
    trades (at its own average R-multiple) it would take to recover."""
    rows = [r for r in _closed_rows(strategy_id, symbol) if r.get("closed_at")]
    if len(rows) < pattern_stats.MIN_SAMPLE_SIZE:
        return {"checked": False,
                "reason": f"only {len(rows)} closed trades so far -- need {pattern_stats.MIN_SAMPLE_SIZE} "
                          f"before a real worst-streak can be measured"}
    rows_sorted = sorted(rows, key=lambda r: r["closed_at"])
    worst_streak = _max_losing_streak(rows_sorted)
    losses = [r for r in rows if r["pnl"] < 0]
    avg_loss = abs(sum(r["pnl"] for r in losses) / len(losses)) if losses else 0.0
    wins = [r for r in rows if r["pnl"] > 0]
    avg_win = (sum(r["pnl"] for r in wins) / len(wins)) if wins else 0.0

    simulated_cost = round(worst_streak * avg_loss, 2)
    recovery_trades_needed = math.ceil(simulated_cost / avg_win) if avg_win > 0 else None
    return {
        "checked": True, "worst_historical_losing_streak": worst_streak,
        "avg_loss_per_trade": round(avg_loss, 2), "avg_win_per_trade": round(avg_win, 2),
        "simulated_cost_if_it_happened_again": simulated_cost,
        "simulated_cost_pct_of_start_amount": round(simulated_cost / start_amount * 100, 2) if start_amount else None,
        "recovery_trades_needed_at_own_avg_win": recovery_trades_needed,
        "note": (
            f"This combination's worst real losing streak on record is {worst_streak} trades in a row "
            f"(avg loss ${avg_loss:.2f} each). If that happened again starting today, it would cost about "
            f"${simulated_cost:.2f}"
            + (f", needing roughly {recovery_trades_needed} more winning trades at its own average win size "
               f"just to recover." if recovery_trades_needed else ".")
        ),
    }


def find_best_historical_period(strategy_id, symbol, window_days):
    """Phase 2.13: the REAL historical window_days-long period (from this
    combination's own trade history) where it grew fastest -- 'here's when
    a similar target was actually achieved, and how' -- never a projection,
    only what already happened. Compounds each window's own real
    R-multiples at the configured risk % to get a genuine growth multiple.
    None if there isn't at least one full window_days span of history yet."""
    rows = [r for r in _closed_rows(strategy_id, symbol) if r.get("closed_at") and r.get("risk_amount")]
    if not rows:
        return None
    rows.sort(key=lambda r: r["closed_at"])
    risk_pct = pt_config.load().get("risk_pct_default", 1.0) / 100.0

    best = None
    for anchor in rows:
        window_start = datetime.fromisoformat(anchor["closed_at"])
        window_end = window_start + timedelta(days=window_days)
        window_trades = [
            r for r in rows
            if window_start <= datetime.fromisoformat(r["closed_at"]) < window_end
        ]
        if len(window_trades) < 2:
            continue
        growth_multiple = 1.0
        for t in window_trades:
            growth_multiple *= (1 + (t["pnl"] / t["risk_amount"]) * risk_pct)
        if best is None or growth_multiple > best["growth_multiple"]:
            best = {
                "window_start": window_start.isoformat(), "window_end": window_end.isoformat(),
                "growth_multiple": round(growth_multiple, 4), "trades_in_window": len(window_trades),
            }
    return best


def replay_challenge(start_amount, target_amount, days_ago_started, strategy_id=None, symbol=None):
    """Phase 2.7: 'if I had started this exact challenge N days/weeks ago,
    what would have happened?' -- uses the exact same real-R-multiple
    compounding math as challenge_multi.compute_compounding_current_amount,
    just anchored to an arbitrary past date instead of a real challenge's
    own started_at, over real trades only."""
    started_at = (datetime.now(timezone.utc) - timedelta(days=days_ago_started)).isoformat()
    rows = _closed_rows(strategy_id, symbol) if (strategy_id and symbol) else _closed_rows()
    trades = sorted(
        (r for r in rows if r.get("closed_at") and r["closed_at"] >= started_at and r.get("risk_amount")),
        key=lambda r: r["closed_at"],
    )
    risk_pct = pt_config.load().get("risk_pct_default", 1.0) / 100.0
    balance = start_amount
    for t in trades:
        r_multiple = t["pnl"] / t["risk_amount"]
        balance += r_multiple * (balance * risk_pct)

    return {
        "started_at": started_at, "ending_amount": round(balance, 2),
        "trades_counted": len(trades), "would_have_reached_target": balance >= target_amount,
    }


def strategy_rotation_suggestion(candidate_strategy_ids=None):
    """Phase 2.16: suggests rotating between two strategies based on real,
    stored per-trade market_state (paper_trading.market_state.classify(),
    recorded at entry time) -- 'use Strategy A when trending, Strategy B
    when ranging' grounded in actual historical regime performance, never
    a guess. Only ever pairs strategies whose OWN best-performing real
    market condition genuinely differs."""
    rows = _closed_rows()
    if candidate_strategy_ids:
        rows = [r for r in rows if r["strategy_id"] in candidate_strategy_ids]

    by_strategy_state = defaultdict(list)
    names = {}
    for r in rows:
        state = r.get("market_state")
        if not state:
            continue
        names[r["strategy_id"]] = r.get("strategy_name") or r["strategy_id"]
        by_strategy_state[(r["strategy_id"], state)].append(r)

    per_strategy_best = {}
    for (sid, state), group in by_strategy_state.items():
        if len(group) < pattern_stats.MIN_SAMPLE_SIZE:
            continue
        m = _metrics_for(group)
        current = per_strategy_best.get(sid)
        if current is None or m["total_pnl"] > current["total_pnl"]:
            per_strategy_best[sid] = {"strategy_id": sid, "strategy_name": names[sid], "best_market_state": state, **m}

    candidates = sorted(per_strategy_best.values(), key=lambda x: -x["total_pnl"])
    if len(candidates) < 2:
        return {"suggestion": None,
                "reason": f"need at least 2 strategies with {pattern_stats.MIN_SAMPLE_SIZE}+ real trades in some "
                          f"single market condition before a rotation can be suggested"}

    for i, a in enumerate(candidates):
        for b in candidates[i + 1:]:
            if a["best_market_state"] != b["best_market_state"]:
                return {
                    "suggestion": {
                        "strategy_a": {"strategy_id": a["strategy_id"], "strategy_name": a["strategy_name"],
                                       "best_in": a["best_market_state"], "win_rate_pct": a["win_rate_pct"],
                                       "total_pnl": a["total_pnl"]},
                        "strategy_b": {"strategy_id": b["strategy_id"], "strategy_name": b["strategy_name"],
                                       "best_in": b["best_market_state"], "win_rate_pct": b["win_rate_pct"],
                                       "total_pnl": b["total_pnl"]},
                    },
                    "reason": (
                        f"{a['strategy_name']} performs best in real '{a['best_market_state']}' conditions, "
                        f"{b['strategy_name']} performs best in real '{b['best_market_state']}' conditions -- "
                        f"based on actual historical trades, not a guess."
                    ),
                }
    return {"suggestion": None,
            "reason": "every strategy with enough per-condition history happens to perform best in the SAME "
                      "real market condition -- no complementary rotation to suggest yet."}
