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
from datetime import datetime, timezone

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
