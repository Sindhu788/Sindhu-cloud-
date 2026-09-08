"""CEO Task 3 -- Independent Paper Trading Groups.

Splits Paper Trading into 3 completely independent groups, each with its
own balance/PnL/win-rate/trade-history, never mixed or averaged together:

  - "losing"      -- strategies currently in loss (real total_pnl < 0)
  - "profitable"  -- strategies currently overall profitable (or new/
                      breakeven, since they haven't lost anything yet)
  - "challenge"   -- the top CHALLENGE_SIZE real performers, with their own
                      daily $CHALLENGE_DAILY_TARGET_USD target (tracking/
                      display only -- no automatic pause/downgrade action)

Deliberately does NOT introduce a second, parallel balance/PnL ledger: a
strategy's real numbers keep coming from the existing per-strategy books
(data_engine.storage's paper_account_state/paper_strategy_performance/
paper_positions -- the same rows the rest of the dashboard already reads
and trusts), so a group can never drift out of sync with what actually
happened. This module only stores a group LABEL per strategy
(paper_strategy_groups) and sums each group's members' already-real rows
at read time.
"""
from datetime import datetime, timedelta, timezone

from data_engine import storage
from paper_trading import config as pt_config

GROUP_KEYS = ("losing", "profitable", "challenge")
GROUP_LABELS = {"losing": "Losing", "profitable": "Profitable", "challenge": "Challenge"}

# How many of the real top performers make up Group C. A strategy needs at
# least one real closed trade to be eligible -- an untested strategy has no
# track record to be a "top performer" on.
CHALLENGE_SIZE = 4

# Group C's own daily target -- tracking/display only, per the CEO's own
# instruction: missing it never pauses or downgrades a strategy.
CHALLENGE_DAILY_TARGET_USD = 2.0

# CEO's own exact marker -- every Telegram SIGNAL (paper_trading.telegram_bot.
# send_signal_for_position) sent for a Group C strategy must end with this,
# and ONLY Group C signals get it, so a Group C alert is instantly visually
# distinguishable from a normal Group A/B one. No extra explanation text
# around it -- just the marker, appended at the very end of the message.
CHALLENGE_TELEGRAM_MARKER = ",,,teen,,,"


def _now():
    return datetime.now(timezone.utc)


def _now_iso():
    return _now().isoformat()


def _day_start_iso(dt):
    return dt.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def _strategy_universe():
    """Every strategy_id that belongs in SOME group: currently enabled in
    Paper Trading, or carrying real closed-trade history (so a strategy
    later disabled doesn't just vanish from its group along with its
    history)."""
    configs = storage.list_paper_strategy_configs()
    enabled_ids = {sid for sid, c in configs.items() if c.get("enabled")}
    stats = storage.list_paper_strategy_stats()
    traded_ids = {s["strategy_id"] for s in stats}
    return enabled_ids | traded_ids, {s["strategy_id"]: s for s in stats}


def sync_group_assignments():
    """Idempotent -- call on every startup. Assigns a group to every
    strategy in _strategy_universe() that doesn't have one yet. Never
    touches an already-assigned strategy, so Group C stays the deliberate,
    stable set it was ranked into rather than reshuffling as new
    strategies are added later.

    On the very first call ever (no strategy has a group yet), this also
    performs the real one-time ranking: top CHALLENGE_SIZE strategies (by
    real total_pnl, requiring at least 1 real closed trade) go to
    "challenge"; every other strategy is split into "losing"/"profitable"
    by its real total_pnl sign. Every subsequent call only fills gaps for
    brand-new strategies (losing/profitable only, by pnl sign -- Challenge
    membership is never auto-expanded after the first run).

    Returns a summary dict {"first_run": bool, "assigned": {group_key: [strategy_id, ...]}}
    for the caller to log -- this is exactly the real evidence the CEO
    asked to see after the migration runs.
    """
    universe, stats_by_id = _strategy_universe()
    already_assigned = storage.list_paper_strategy_groups()
    first_run = len(already_assigned) == 0
    to_assign = sorted(universe - set(already_assigned))
    if not to_assign:
        return {"first_run": first_run, "assigned": {k: [] for k in GROUP_KEYS}}

    now_iso = _now_iso()
    assigned = {k: [] for k in GROUP_KEYS}

    if first_run:
        eligible_for_challenge = sorted(
            (sid for sid in to_assign if stats_by_id.get(sid, {}).get("closed_trades", 0) > 0),
            key=lambda sid: stats_by_id[sid]["total_pnl"],
            reverse=True,
        )
        challenge_ids = set(eligible_for_challenge[:CHALLENGE_SIZE])
        for sid in to_assign:
            if sid in challenge_ids:
                group_key = "challenge"
            else:
                pnl = stats_by_id.get(sid, {}).get("total_pnl", 0.0)
                group_key = "losing" if pnl < 0 else "profitable"
            storage.upsert_paper_strategy_group(sid, group_key, now_iso, auto_assigned=True)
            assigned[group_key].append(sid)
    else:
        for sid in to_assign:
            pnl = stats_by_id.get(sid, {}).get("total_pnl", 0.0)
            group_key = "losing" if pnl < 0 else "profitable"
            storage.upsert_paper_strategy_group(sid, group_key, now_iso, auto_assigned=True)
            assigned[group_key].append(sid)

    return {"first_run": first_run, "assigned": assigned}


def get_group(strategy_id):
    """This strategy's assigned group, or None if it has never been
    assigned one (sync_group_assignments() hasn't seen it yet -- e.g. it
    hasn't been enabled in Paper Trading or closed a trade)."""
    return storage.list_paper_strategy_groups().get(strategy_id)


def members_of(group_key):
    assignments = storage.list_paper_strategy_groups()
    return [sid for sid, g in assignments.items() if g == group_key]


def _strategy_names():
    try:
        from backtest_engine import strategy_library as lib
        return {m["id"]: m["name"] for m in lib.list_all()}
    except Exception:
        return {}


def group_summary(group_key):
    """Real, independently-computed balance/PnL/win-rate/trade-count for
    one group -- summed from its members' own already-real per-strategy
    rows, never averaged or blended with another group's numbers."""
    if group_key not in GROUP_KEYS:
        raise ValueError(f"Unknown group {group_key!r} -- must be one of {GROUP_KEYS}")

    members = members_of(group_key)
    member_set = set(members)
    initial_balance = pt_config.load().get("initial_balance", 10000.0)
    states_by_id = {s["strategy_id"]: s for s in storage.list_paper_account_states()}
    stats_by_id = {s["strategy_id"]: s for s in storage.list_paper_strategy_stats()}
    names = _strategy_names()

    total_pnl = sum(states_by_id.get(sid, {}).get("realized_pnl_total", 0.0) for sid in members)
    trades = sum(states_by_id.get(sid, {}).get("closed_count", 0) for sid in members)
    wins = sum(states_by_id.get(sid, {}).get("win_count", 0) for sid in members)
    open_positions = [p for p in storage.get_open_paper_positions() if p.get("strategy_id") in member_set]

    strategies = []
    for sid in members:
        st = stats_by_id.get(sid, {})
        acct = states_by_id.get(sid, {})
        strategies.append({
            "strategy_id": sid,
            "strategy_name": names.get(sid) or st.get("strategy_name") or sid,
            "balance": round(initial_balance + acct.get("realized_pnl_total", 0.0), 2),
            "total_pnl": round(acct.get("realized_pnl_total", 0.0), 2),
            "closed_trades": acct.get("closed_count", 0),
            "win_rate_pct": st.get("win_rate", 0.0),
        })
    strategies.sort(key=lambda s: s["total_pnl"], reverse=True)

    return {
        "group_key": group_key,
        "label": GROUP_LABELS[group_key],
        "strategy_count": len(members),
        "balance": round(initial_balance * len(members) + total_pnl, 2),
        "total_pnl": round(total_pnl, 2),
        "closed_trades": trades,
        "win_count": wins,
        "win_rate_pct": round(wins / trades * 100, 2) if trades else 0.0,
        "open_positions": len(open_positions),
        "strategies": strategies,
    }


def all_group_summaries():
    return {group_key: group_summary(group_key) for group_key in GROUP_KEYS}


def challenge_daily_status(now=None):
    """Today's real closed-trade PnL for Group C vs. its
    $CHALLENGE_DAILY_TARGET_USD target. Tracking/display only -- reading
    this never pauses or changes anything."""
    now = now or _now()
    members = members_of("challenge")
    today_start = _day_start_iso(now)
    pnl_today = storage.sum_paper_pnl_for_strategies_since(members, today_start)
    return {
        "date": now.date().isoformat(),
        "target_usd": CHALLENGE_DAILY_TARGET_USD,
        "pnl_today": round(pnl_today, 2),
        "hit": pnl_today >= CHALLENGE_DAILY_TARGET_USD,
    }


def challenge_recent_days(n_days=14, now=None):
    """Day-by-day hit/miss history for Group C's daily target, oldest
    first -- powers the "hit it every day, consistently" dashboard view.
    A day with no closed trade at all is reported as has_data=False rather
    than a false "$0, missed" -- silence isn't the same claim as a real
    $0 result."""
    now = now or _now()
    members = members_of("challenge")
    since = _day_start_iso(now - timedelta(days=n_days - 1))
    daily = storage.daily_paper_pnl_for_strategies(members, since)

    days = []
    for i in range(n_days):
        day = (now - timedelta(days=n_days - 1 - i)).date().isoformat()
        has_data = day in daily
        pnl = daily.get(day)
        days.append({
            "date": day,
            "has_data": has_data,
            "pnl": round(pnl, 2) if has_data else None,
            "hit": has_data and pnl >= CHALLENGE_DAILY_TARGET_USD,
        })
    return days
