"""Batch 9, Task 4: Challenge Mode -- a personal target the CEO sets
themselves (starting amount, target amount, time period in days),
tracked against the system's REAL demonstrated performance. This module
is tracking/reporting ONLY: it never touches risk_pct, position sizing,
entry conditions, or any other trading behavior, and nothing here is
read by the trading engine.

Honesty is the whole point: the required pace to hit the target is
compared against a REAL daily rate derived from real closed paper
trades (median R-multiple, real trade frequency, real configured risk
%) -- the exact same real-R-multiple-rescaling technique
paper_trading.telegram_analytics.hypothetical_pnl already uses for its
own hypothetical account, just generalized to the CEO's own chosen
starting amount instead of a fixed $100, and expressed as a rate
instead of a lump sum. If the required pace is far beyond what the
system has ever actually shown, that is stated plainly rather than
presented as achievable.
"""

import math
from datetime import datetime, timedelta, timezone

from data_engine import config as base_config, storage
from paper_trading import config as pt_config

_SETTINGS_FILE = "challenge_settings.json"
_DEFAULTS = {
    "enabled": False,
    "start_amount": None,
    "target_amount": None,
    "days": None,
    "started_at": None,
    "telegram_report_enabled": False,
    # Level 3 (one-click start from a recommended path): when set, this
    # challenge tracks ONE specific real strategy-coin combination's own
    # trades instead of the system-wide blended pace -- the exact fix for
    # the original single-aggregate design flaw. None/None (the default)
    # preserves the original system-wide behavior for anyone who never
    # touches this. baseline_win_rate_pct is captured once at start time
    # so later drift can be judged against what was true when the CEO
    # actually started the challenge, not a constantly-shifting number.
    "scope_strategy_id": None,
    "scope_symbol": None,
    "baseline_win_rate_pct": None,
}

# A required daily pace more than this many times the system's own real
# demonstrated daily rate is called out as unrealistic outright, rather
# than left for the CEO to infer by comparing two raw percentages.
UNREALISTIC_MULTIPLE = 2.0


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def load():
    return base_config.load_or_seed(_SETTINGS_FILE, _DEFAULTS)


def save(settings):
    base_config.save_config(_SETTINGS_FILE, settings)


def set_challenge(start_amount, target_amount, days, telegram_report_enabled=False, now_iso=None,
                   scope_strategy_id=None, scope_symbol=None):
    """Every number here is chosen by the CEO -- nothing hardcoded.
    Starting a new challenge always resets started_at to now, discarding
    any prior challenge's progress (a fresh target needs a fresh clock).

    scope_strategy_id/scope_symbol (Level 3 -- one-click start from a
    recommended path): optional. When both are given, this challenge
    tracks that ONE real strategy-coin combination's own trades instead
    of the system-wide blended pace. Starting a challenge -- scoped or
    not -- NEVER alters risk_pct, position sizing, or any trading
    behavior; it only changes what this tracking layer reads."""
    if start_amount is None or target_amount is None or days is None:
        raise ValueError("start_amount, target_amount, and days are all required")
    start_amount = float(start_amount)
    target_amount = float(target_amount)
    days = int(days)
    if start_amount <= 0 or days <= 0:
        raise ValueError("start_amount and days must both be positive")

    baseline_win_rate_pct = None
    if scope_strategy_id and scope_symbol:
        from paper_trading import challenge_analysis
        rows = challenge_analysis._closed_rows(scope_strategy_id, scope_symbol)
        if rows:
            wins = sum(1 for r in rows if r["pnl"] > 0)
            baseline_win_rate_pct = round(wins / len(rows) * 100, 2)

    settings = {
        "enabled": True, "start_amount": start_amount, "target_amount": target_amount,
        "days": days, "started_at": now_iso or _now_iso(),
        "telegram_report_enabled": bool(telegram_report_enabled),
        "scope_strategy_id": scope_strategy_id, "scope_symbol": scope_symbol,
        "baseline_win_rate_pct": baseline_win_rate_pct,
    }
    save(settings)
    return settings


def clear_challenge():
    save(dict(_DEFAULTS))


def _required_daily_rate(start_amount, target_amount, days):
    """Compound daily growth rate needed to go from start to target in
    `days` days -- e.g. 0.01 means 1%/day. 0.0 for a non-positive/already
    at-or-past-target case rather than raising or returning something
    nonsensical (e.g. a negative-under-a-root)."""
    if start_amount <= 0 or days <= 0 or target_amount <= start_amount:
        return 0.0
    return (target_amount / start_amount) ** (1.0 / days) - 1.0


def _real_demonstrated_daily_rate():
    """The system's own REAL demonstrated pace, all-time, every strategy
    combined: real median R-multiple per closed trade * real configured
    risk % per trade * real trades-per-day frequency. Returns
    (daily_rate_or_None, closed_trades, earliest_activity_iso_or_None) --
    daily_rate is None when there isn't yet a single real closed trade to
    honestly measure a pace from."""
    summary = storage.get_paper_period_summary()
    earliest = storage.earliest_paper_trading_activity()
    if not summary["closed_trades"] or not earliest:
        return None, summary["closed_trades"], earliest
    elapsed_days = max(1.0, (datetime.now(timezone.utc) - datetime.fromisoformat(earliest)).total_seconds() / 86400)
    trades_per_day = summary["closed_trades"] / elapsed_days
    risk_pct = pt_config.load().get("risk_pct_default", 1.0) / 100.0
    avg_rr = summary["avg_rr"] if summary["avg_rr"] is not None else 0.0
    return avg_rr * risk_pct * trades_per_day, summary["closed_trades"], earliest


def _current_amount(start_amount, started_at):
    """Same real-R-multiple rescaling technique as telegram_analytics.
    hypothetical_pnl, generalized to the challenge's own chosen starting
    amount and applied to every REAL closed paper trade system-wide
    (not just Telegram-sent ones) since the challenge started: "if this
    account had been live since you started the challenge, riding the
    exact same real trades this system actually took, here's where it
    would be today." Never a projection -- only real, already-recorded
    outcomes count."""
    risk_pct = pt_config.load().get("risk_pct_default", 1.0) / 100.0
    risk_per_trade = start_amount * risk_pct
    trades = storage.list_closed_paper_trades_since(started_at)
    total_pnl = 0.0
    counted = 0
    for t in trades:
        if not t.get("risk_amount"):
            continue
        r_multiple = t["pnl"] / t["risk_amount"]
        total_pnl += r_multiple * risk_per_trade
        counted += 1
    return start_amount + total_pnl, counted


def _scoped_daily_rate(scope_strategy_id, scope_symbol):
    """Same shape as _real_demonstrated_daily_rate(), but for ONE specific
    real strategy-coin combination instead of the system-wide blend --
    the Level 3 "one-click start from a recommended path" tracking mode.
    Returns (daily_rate_or_None, closed_trades, baseline_win_rate_pct)."""
    from paper_trading import challenge_analysis
    daily_rate, _avg_r, _tpd = challenge_analysis._combo_daily_rate(scope_strategy_id, scope_symbol)
    rows = challenge_analysis._closed_rows(scope_strategy_id, scope_symbol)
    closed_trades = len(rows)
    win_rate_pct = round(sum(1 for r in rows if r["pnl"] > 0) / closed_trades * 100, 2) if closed_trades else None
    return daily_rate, closed_trades, win_rate_pct


def _scoped_current_amount(start_amount, started_at, scope_strategy_id, scope_symbol):
    """Same real-R-multiple rescaling as _current_amount(), restricted to
    ONE real strategy-coin combination's own closed trades since the
    challenge started. list_closed_paper_trades_since() only returns
    pnl/risk_amount (no strategy_id/symbol), so this reuses
    challenge_analysis._closed_rows() (full rows, already strategy/coin
    filtered) and applies the since-started_at filter itself."""
    from paper_trading import challenge_analysis
    risk_pct = pt_config.load().get("risk_pct_default", 1.0) / 100.0
    risk_per_trade = start_amount * risk_pct
    trades = [
        t for t in challenge_analysis._closed_rows(scope_strategy_id, scope_symbol)
        if t.get("closed_at") and t["closed_at"] >= started_at
    ]
    total_pnl = 0.0
    counted = 0
    for t in trades:
        if not t.get("risk_amount"):
            continue
        r_multiple = t["pnl"] / t["risk_amount"]
        total_pnl += r_multiple * risk_per_trade
        counted += 1
    return start_amount + total_pnl, counted


def _projected_finish_date(start_amount, target_amount, current_amount, elapsed_days, now):
    """Level 3: projected finish date based on the REAL realized pace
    observed so far (current_amount's actual growth over elapsed_days),
    not the original required-pace assumption. Returns (iso_date_or_None,
    realized_daily_rate_or_None). None when there isn't yet a meaningful
    realized rate to extrapolate from (too little elapsed time, or no
    net growth yet)."""
    if elapsed_days < 1.0 or current_amount <= start_amount or start_amount <= 0:
        return None, None
    if current_amount >= target_amount:
        return now.isoformat(), None
    realized_daily_rate = (current_amount / start_amount) ** (1.0 / elapsed_days) - 1.0
    if realized_daily_rate <= 0:
        return None, realized_daily_rate
    additional_days = math.log(target_amount / current_amount) / math.log(1 + realized_daily_rate)
    return (now + timedelta(days=additional_days)).isoformat(), realized_daily_rate


def _honest_note(required_daily_rate, real_daily_rate, closed_trades, realistic):
    if real_daily_rate is None:
        return ("Abhi tak paper trading mein koi trade band nahi hua, isliye system ki real pace se "
                "compare nahi kiya ja sakta -- yeh sirf target ka hisaab hai, koi guarantee nahi.")
    if realistic:
        return (
            f"Yeh target din mein {required_daily_rate * 100:.2f}% chahta hai, aur system ka real "
            f"demonstrated daily rate {real_daily_rate * 100:.2f}% raha hai ({closed_trades} real closed "
            f"trades se) -- yeh pace system ki real history ke mutabiq mumkin nazar aata hai, lekin koi "
            f"guarantee nahi hai."
        )
    if real_daily_rate <= 0:
        return (
            f"Yeh target din mein {required_daily_rate * 100:.2f}% chahta hai, lekin system ka real "
            f"demonstrated daily rate abhi {real_daily_rate * 100:.2f}% hai ({closed_trades} real closed "
            f"trades se) -- kisi bhi strategy ne is tarah ka return abhi tak nahi dikhaya. Yeh target is "
            f"waqt REALISTIC NAHI hai."
        )
    multiple = required_daily_rate / real_daily_rate
    return (
        f"Yeh target din mein {required_daily_rate * 100:.2f}% chahta hai, jabke system ka real "
        f"demonstrated daily rate ab tak sirf {real_daily_rate * 100:.2f}% raha hai ({closed_trades} real "
        f"closed trades se) -- zaroori pace real pace se {multiple:.1f}x zyada hai. Yeh target is waqt "
        f"REALISTIC NAHI hai kisi bhi mojooda strategy ke through -- risk badhane se yeh haqiqi nahi ban "
        f"jaata, sirf nuksan ka khatra badh jaata hai."
    )


def compute_progress(now_iso=None):
    """Returns None if no challenge is currently configured/enabled.
    Otherwise a full, honest status dict. Read-only: never writes
    anything, never touches risk_pct/position sizing/any trading
    behavior."""
    settings = load()
    if not settings.get("enabled") or not settings.get("start_amount"):
        return None

    start_amount = settings["start_amount"]
    target_amount = settings["target_amount"]
    days = settings["days"]
    started_at = settings["started_at"]

    now = datetime.fromisoformat(now_iso) if now_iso else datetime.now(timezone.utc)
    started = datetime.fromisoformat(started_at)
    elapsed_days = max(0.0, (now - started).total_seconds() / 86400)
    remaining_days = max(0.0, days - elapsed_days)

    scope_strategy_id = settings.get("scope_strategy_id")
    scope_symbol = settings.get("scope_symbol")
    scoped = bool(scope_strategy_id and scope_symbol)

    required_daily_rate = _required_daily_rate(start_amount, target_amount, days)
    if scoped:
        real_daily_rate, closed_trades, _win_rate = _scoped_daily_rate(scope_strategy_id, scope_symbol)
        current_amount, trades_counted = _scoped_current_amount(start_amount, started_at, scope_strategy_id, scope_symbol)
    else:
        real_daily_rate, closed_trades, _earliest = _real_demonstrated_daily_rate()
        current_amount, trades_counted = _current_amount(start_amount, started_at)
    realistic = None if real_daily_rate is None else required_daily_rate <= real_daily_rate * UNREALISTIC_MULTIPLE

    span = target_amount - start_amount
    if span == 0:
        progress_pct = 100.0
    else:
        progress_pct = max(0.0, min(100.0, (current_amount - start_amount) / span * 100))

    expected_amount_by_now = start_amount * ((1 + required_daily_rate) ** elapsed_days)
    ahead_of_pace = current_amount >= expected_amount_by_now

    projected_finish_date, realized_daily_rate = _projected_finish_date(
        start_amount, target_amount, current_amount, elapsed_days, now)

    drift = None
    if scoped and settings.get("baseline_win_rate_pct") is not None:
        from paper_trading import challenge_analysis
        drift = challenge_analysis.check_drift(scope_strategy_id, scope_symbol, settings["baseline_win_rate_pct"])

    return {
        "start_amount": start_amount, "target_amount": target_amount, "days": days,
        "started_at": started_at, "elapsed_days": round(elapsed_days, 2),
        "remaining_days": round(remaining_days, 2),
        "current_amount": round(current_amount, 2), "trades_counted": trades_counted,
        "progress_pct": round(progress_pct, 2),
        "required_daily_rate_pct": round(required_daily_rate * 100, 4),
        "real_demonstrated_daily_rate_pct": round(real_daily_rate * 100, 4) if real_daily_rate is not None else None,
        "closed_trades_used_for_baseline": closed_trades,
        "realistic": realistic,
        "ahead_of_pace": ahead_of_pace,
        "expected_amount_by_now": round(expected_amount_by_now, 2),
        "honest_note": _honest_note(required_daily_rate, real_daily_rate, closed_trades, realistic),
        "telegram_report_enabled": settings.get("telegram_report_enabled", False),
        # Level 3 additions -- always present (None when not applicable),
        # never breaking the original unscoped shape above.
        "scope_strategy_id": scope_strategy_id, "scope_symbol": scope_symbol,
        "projected_finish_date": projected_finish_date,
        "realized_daily_rate_pct": round(realized_daily_rate * 100, 4) if realized_daily_rate is not None else None,
        "drift": drift,
    }
