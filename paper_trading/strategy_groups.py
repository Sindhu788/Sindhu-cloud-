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
# least one real closed trade OR a completed backtest to be eligible -- an
# untested strategy has no track record to be a "top performer" on.
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

    Every new strategy is split into "losing"/"profitable" by its real
    effective PnL sign (see _effective_pnl). Separately, whenever Challenge
    is still empty, the top CHALLENGE_SIZE strategies with real data
    (across the WHOLE universe, not just brand-new ones) are ranked into
    "challenge" -- see the challenge-backfill comment below for why this
    is no longer tied to first_run specifically. Once Challenge has any
    real member, it is never reshuffled again.

    Returns a summary dict {"first_run": bool, "assigned": {group_key: [strategy_id, ...]},
    "reclassified": int, "challenge_backfilled": int} for the caller to
    log -- this is exactly the real evidence the CEO asked to see after
    the migration runs.
    """
    universe, stats_by_id = _strategy_universe()
    already_assigned = storage.list_paper_strategy_groups_with_auto_assigned()
    first_run = len(already_assigned) == 0
    to_assign = sorted(universe - set(already_assigned))

    now_iso = _now_iso()
    assigned = {k: [] for k in GROUP_KEYS}
    new_assignments = {}

    # Fix, 2026-09-12: ranking used to be keyed only on live paper-trading
    # PnL (stats_by_id), which takes real trades days/weeks to accumulate --
    # a freshly-enabled strategy with a genuinely strong backtest record
    # looked identical to one with zero history (both defaulted to
    # pnl=0.0, "profitable", never Challenge-eligible) until it closed its
    # first live trade. _effective_pnl() prefers live PnL once it's real,
    # otherwise falls back to the strategy's own backtest net PnL, so
    # groups populate immediately from data that already exists. The
    # one-time Challenge ranking rule itself is unchanged -- only what it
    # ranks on. Computed for the whole universe (not just to_assign) since
    # it also feeds the reclassification pass below.
    backtest_pnl_by_id = _strategy_backtest_net_pnl()
    pnl_cache = {sid: _effective_pnl(sid, stats_by_id, backtest_pnl_by_id) for sid in universe}

    for sid in to_assign:
        pnl, _ = pnl_cache[sid]
        group_key = "losing" if pnl < 0 else "profitable"
        new_assignments[sid] = group_key
        assigned[group_key].append(sid)

    # Reclassify EXISTING losing/profitable members using the same
    # effective-PnL logic -- Challenge is deliberately excluded (that
    # membership stays the stable set it was ranked into, per this
    # function's own docstring), and so is any MANUAL override (a CEO
    # deliberately moving a strategy via POST /groups/{id}/move,
    # auto_assigned=False) -- test_manual_move_overrides_and_sticks
    # requires a later sync never undoes a deliberate manual choice. Only
    # an auto-assigned "profitable" purely because it had zero data (the
    # old pnl=0.0 default) the moment it was first assigned should move to
    # "losing" the instant real data (its backtest net PnL, or its first
    # live loss) says otherwise, instead of freezing there forever.
    # Idempotent -- a no-op once every auto-assigned member's bucket
    # already matches its real current data.
    reclassified = {}
    for sid, entry in already_assigned.items():
        group_key = entry["group_key"]
        if group_key == "challenge" or not entry["auto_assigned"] or sid not in pnl_cache:
            continue
        pnl, has_data = pnl_cache[sid]
        if not has_data:
            continue
        correct_key = "losing" if pnl < 0 else "profitable"
        if correct_key != group_key:
            reclassified[sid] = correct_key

    # ONE connection per batch -- see upsert_paper_strategy_groups_batch's
    # docstring for why a per-strategy loop here (on top of the same shape
    # of loop enable-all's own activation write already had) mattered
    # enough to fix.
    # Challenge backfill. Bug fixed 2026-09-12, confirmed via Render logs
    # (zero Challenge-tagged Telegram signals ever sent despite 1000+ real
    # trades): Challenge used to be ranked ONLY on the very first sync ever
    # (first_run), which on a fresh deployment can happen -- and here,
    # did happen -- before any strategy had real performance data, so
    # `eligible_for_challenge` was empty and Challenge was permanently
    # stuck at 0 members forever after (the old rule never revisited it).
    # This runs instead whenever Challenge is STILL EMPTY and the universe
    # now has at least one strategy with real data (live or backtest PnL)
    # to rank on -- a strategy already auto-assigned elsewhere is moved
    # into Challenge (never a manually-overridden one); once Challenge has
    # any real member, this never runs again, preserving the original
    # "ranked once, then stable" guarantee -- just correctly deferred
    # until it can be computed from real data instead of from nothing.
    challenge_members = {sid for sid, e in already_assigned.items() if e["group_key"] == "challenge"}
    challenge_backfill = {}
    if not challenge_members:
        candidates = sorted(
            (sid for sid in universe if pnl_cache[sid][1]
             and (sid not in already_assigned or already_assigned[sid]["auto_assigned"])),
            key=lambda sid: pnl_cache[sid][0],
            reverse=True,
        )
        for sid in candidates[:CHALLENGE_SIZE]:
            challenge_backfill[sid] = "challenge"
            new_assignments.pop(sid, None)
            for key in GROUP_KEYS:
                if sid in assigned[key]:
                    assigned[key].remove(sid)
            assigned["challenge"].append(sid)

    if new_assignments:
        storage.upsert_paper_strategy_groups_batch(new_assignments, now_iso, auto_assigned=True)
    if reclassified:
        storage.upsert_paper_strategy_groups_batch(reclassified, now_iso, auto_assigned=True)
        for sid, group_key in reclassified.items():
            assigned[group_key].append(sid)
    if challenge_backfill:
        storage.upsert_paper_strategy_groups_batch(challenge_backfill, now_iso, auto_assigned=True)

    return {"first_run": first_run, "assigned": assigned, "reclassified": len(reclassified),
            "challenge_backfilled": len(challenge_backfill)}


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


def _strategy_backtest_net_pnl():
    """{strategy_id: net_pnl} from each strategy's git-tracked backtest
    snapshot (backtest_engine.strategy_library.save_backtest_snapshot,
    refreshed opportunistically whenever the Strategies/Backtesting page
    computes these same numbers) -- deliberately NOT a live query against
    backtest_batches/backtest_results, which the cloud runner's Postgres
    schema excludes entirely (see data_engine/db_backend.py's
    POSTGRES_SCHEMA docstring) and which would throw UndefinedTable on
    every call there. meta.json already travels from the local machine to
    the cloud deploy via the normal git commit/push, so this is real
    backtest data without a live DB dependency. A strategy with no
    completed backtest yet (or an older snapshot saved before net_pnl was
    added to it) simply has no entry here."""
    try:
        from backtest_engine import strategy_library as lib
        return {
            m["id"]: m["backtest_snapshot"]["net_pnl"]
            for m in lib.list_all()
            if m.get("backtest_snapshot") and m["backtest_snapshot"].get("net_pnl") is not None
        }
    except Exception:
        return {}


def _effective_pnl(sid, stats_by_id, backtest_pnl_by_id):
    """(pnl, has_real_data) for ranking/grouping purposes: real live
    paper-trading PnL once this strategy has actually closed a trade
    (the authoritative number once it exists), falling back to its real
    backtest net PnL so Losing/Profitable/Challenge can populate
    immediately from data that already exists rather than waiting weeks
    for enough live paper trades to close. A strategy with neither yet
    gets a neutral 0.0/no-data reading (not eligible for Challenge, lands
    in "profitable" by the same not-yet-proven-losing default the
    live-only version always used)."""
    live = stats_by_id.get(sid, {})
    if live.get("closed_trades", 0) > 0:
        return live["total_pnl"], True
    if sid in backtest_pnl_by_id:
        return backtest_pnl_by_id[sid], True
    return 0.0, False


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
