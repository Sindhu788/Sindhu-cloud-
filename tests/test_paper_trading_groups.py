"""CEO Task 3 -- Independent Paper Trading Groups (paper_trading/strategy_groups.py).

Covers: real-data-based auto-migration into losing/profitable/challenge,
idempotency (never reshuffles an already-assigned strategy), per-group
balance/PnL/win-rate aggregation with zero cross-contamination between
groups, and the Challenge group's daily $ target tracking.
"""
from datetime import datetime, timedelta, timezone

from data_engine import storage
from paper_trading import strategy_groups


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _enable_strategy(strategy_id, now_iso=None):
    storage.save_paper_strategy_config(strategy_id, True, 5, [], [], now_iso or _now_iso())


def _close_trade(strategy_id, pnl, closed_at=None):
    closed_at = closed_at or _now_iso()
    with storage.get_conn() as conn:
        conn.execute(
            """INSERT INTO paper_positions
               (id, exchange, symbol, direction, entry_price, size, entry_time,
                pnl, status, strategy_id, strategy_name, created_at, closed_at)
               VALUES (?, 'binance', 'BTCUSDT', 'long', 100, 1, 0, ?, 'closed', ?, ?, ?, ?)""",
            (f"{strategy_id}-{closed_at}-{pnl}", pnl, strategy_id, strategy_id, closed_at, closed_at),
        )
        conn.execute(
            """INSERT INTO paper_account_state (strategy_id, realized_pnl_total, closed_count, win_count, updated_at)
               VALUES (?, ?, 1, ?, ?)
               ON CONFLICT(strategy_id) DO UPDATE SET
                 realized_pnl_total = realized_pnl_total + excluded.realized_pnl_total,
                 closed_count = closed_count + 1,
                 win_count = win_count + excluded.win_count,
                 updated_at = excluded.updated_at""",
            (strategy_id, pnl, 1 if pnl > 0 else 0, closed_at),
        )


def test_first_sync_ranks_top_performers_into_challenge(test_db, monkeypatch):
    monkeypatch.setattr(strategy_groups, "CHALLENGE_SIZE", 2)
    # 6 strategies: 2 clearly losing, 2 clearly profitable-but-not-top,
    # and 2 clear top performers that must land in Challenge.
    for sid, pnl in [("loser1", -50), ("loser2", -20)]:
        _enable_strategy(sid)
        _close_trade(sid, pnl)
    for sid, pnl in [("mid1", 10), ("mid2", 15)]:
        _enable_strategy(sid)
        _close_trade(sid, pnl)
    for sid, pnl in [("top1", 500), ("top2", 400)]:
        _enable_strategy(sid)
        _close_trade(sid, pnl)

    result = strategy_groups.sync_group_assignments()

    assert result["first_run"] is True
    assignments = storage.list_paper_strategy_groups()
    assert assignments["loser1"] == "losing"
    assert assignments["loser2"] == "losing"
    assert assignments["mid1"] == "profitable"
    assert assignments["mid2"] == "profitable"
    # Only room for CHALLENGE_SIZE=4 -- both top performers must fit, and
    # neither a loser nor a mid strategy should have been promoted instead.
    assert assignments["top1"] == "challenge"
    assert assignments["top2"] == "challenge"


def test_second_sync_never_reshuffles_existing_assignments(test_db):
    _enable_strategy("top1")
    _close_trade("top1", 500)
    strategy_groups.sync_group_assignments()
    assert storage.list_paper_strategy_groups()["top1"] == "challenge"

    # top1 has a catastrophic loss now -- but an already-assigned strategy
    # must NEVER be auto-moved out of its group by a later sync.
    _close_trade("top1", -1000)
    strategy_groups.sync_group_assignments()
    assert storage.list_paper_strategy_groups()["top1"] == "challenge"


def test_new_strategy_after_first_run_never_auto_joins_challenge(test_db):
    _enable_strategy("top1")
    _close_trade("top1", 500)
    strategy_groups.sync_group_assignments()

    # A brand-new strategy appears later with an even bigger real pnl --
    # it must go to losing/profitable only, never auto-promoted to
    # Challenge (that stays a deliberate, one-time-ranked set).
    _enable_strategy("newcomer")
    _close_trade("newcomer", 9999)
    result = strategy_groups.sync_group_assignments()

    assert result["first_run"] is False
    assert storage.list_paper_strategy_groups()["newcomer"] == "profitable"


def test_groups_never_mix_or_average_each_others_numbers(test_db, monkeypatch):
    monkeypatch.setattr(strategy_groups, "CHALLENGE_SIZE", 0)
    for sid, pnl in [("loser1", -50)]:
        _enable_strategy(sid)
        _close_trade(sid, pnl)
    for sid, pnl in [("mid1", 30)]:
        _enable_strategy(sid)
        _close_trade(sid, pnl)
    strategy_groups.sync_group_assignments()

    losing = strategy_groups.group_summary("losing")
    profitable = strategy_groups.group_summary("profitable")

    assert losing["total_pnl"] == -50
    assert losing["strategy_count"] == 1
    assert profitable["total_pnl"] == 30
    assert profitable["strategy_count"] == 1
    # Neither group's number leaked into the other.
    assert losing["total_pnl"] != profitable["total_pnl"]
    losing_ids = {s["strategy_id"] for s in losing["strategies"]}
    profitable_ids = {s["strategy_id"] for s in profitable["strategies"]}
    assert losing_ids.isdisjoint(profitable_ids)


def test_challenge_backfills_once_real_data_exists_even_if_first_run_had_none(test_db, monkeypatch):
    """Real bug, confirmed live via Render logs (zero Challenge-tagged
    Telegram signals ever sent despite 1000+ real trades): the very first
    sync can run before any strategy has real data (a fresh deployment
    with nothing enabled/traded yet) -- first_run flips to False right
    then, and the OLD code never revisited Challenge after that, leaving
    it permanently empty. Challenge must still populate for real once
    data actually shows up, even on a later, non-first-run sync."""
    monkeypatch.setattr(strategy_groups, "CHALLENGE_SIZE", 2)
    # Simulates the empty first-ever sync: nothing enabled, nothing traded.
    result = strategy_groups.sync_group_assignments()
    assert result["first_run"] is True
    assert storage.list_paper_strategy_groups() == {}
    # Nothing was written -- so a second empty sync is STILL "first_run"
    # (matches the real Render logs, which showed first_run=True on 3
    # separate calls before anything was ever actually assigned).
    assert strategy_groups.sync_group_assignments()["first_run"] is True

    # A strategy shows up with no data yet -- still no eligible candidate,
    # so Challenge stays empty and first_run finally flips False.
    _enable_strategy("newcomer")
    strategy_groups.sync_group_assignments()
    assert storage.list_paper_strategy_groups()["newcomer"] == "profitable"
    assert strategy_groups.sync_group_assignments()["first_run"] is False

    # Real top performers show up much later -- Challenge must still
    # populate for real from them, well after first_run.
    _enable_strategy("top1")
    _close_trade("top1", 500)
    _enable_strategy("top2")
    _close_trade("top2", 400)
    _enable_strategy("mid1")
    _close_trade("mid1", 10)
    result = strategy_groups.sync_group_assignments()
    assert result["challenge_backfilled"] == 2
    assignments = storage.list_paper_strategy_groups()
    assert assignments["top1"] == "challenge"
    assert assignments["top2"] == "challenge"
    # mid1 has real data too but isn't a top-2 performer -- untouched.
    assert assignments["mid1"] == "profitable"


def test_challenge_backfill_can_promote_an_already_assigned_strategy(test_db, monkeypatch):
    """A strategy assigned "profitable" during the data-less first run
    (the old permanent-placeholder default) must be promotable into
    Challenge once the backfill runs, since it was never a deliberate
    choice -- just the absence of data at the time."""
    monkeypatch.setattr(strategy_groups, "CHALLENGE_SIZE", 1)
    _enable_strategy("futuretop")
    strategy_groups.sync_group_assignments()
    assert storage.list_paper_strategy_groups()["futuretop"] == "profitable"

    _close_trade("futuretop", 1000)
    result = strategy_groups.sync_group_assignments()
    assert result["challenge_backfilled"] == 1
    assert storage.list_paper_strategy_groups()["futuretop"] == "challenge"


def test_challenge_backfill_never_overrides_a_manual_move(test_db, monkeypatch):
    monkeypatch.setattr(strategy_groups, "CHALLENGE_SIZE", 1)
    _enable_strategy("manualpick")
    _close_trade("manualpick", 1000)
    strategy_groups.sync_group_assignments()
    assert storage.list_paper_strategy_groups()["manualpick"] == "challenge"

    # CEO manually moves it back out of Challenge.
    storage.upsert_paper_strategy_groups_batch({"manualpick": "profitable"}, _now_iso(), auto_assigned=False)
    # Challenge is empty again -- a naive backfill could try to re-promote
    # manualpick right back in, undoing the deliberate manual choice.
    result = strategy_groups.sync_group_assignments()
    assert storage.list_paper_strategy_groups()["manualpick"] == "profitable"
    assert result["challenge_backfilled"] == 0


def test_challenge_never_backfills_twice(test_db, monkeypatch):
    monkeypatch.setattr(strategy_groups, "CHALLENGE_SIZE", 1)
    _enable_strategy("top1")
    _close_trade("top1", 500)
    strategy_groups.sync_group_assignments()
    assert storage.list_paper_strategy_groups()["top1"] == "challenge"

    _enable_strategy("evenbigger")
    _close_trade("evenbigger", 9999)
    result = strategy_groups.sync_group_assignments()
    assert result["challenge_backfilled"] == 0
    assert storage.list_paper_strategy_groups()["evenbigger"] == "profitable"
    assert storage.list_paper_strategy_groups()["top1"] == "challenge"


def test_challenge_daily_status_hit_and_miss(test_db):
    now = datetime.now(timezone.utc)
    # Seed trade that earns "champ" its Challenge spot -- closed days ago,
    # so it never contaminates "today"'s target check below.
    _enable_strategy("champ")
    _close_trade("champ", 500, closed_at=(now - timedelta(days=3)).isoformat())
    strategy_groups.sync_group_assignments()
    assert storage.list_paper_strategy_groups()["champ"] == "challenge"

    _close_trade("champ", 3.0, closed_at=now.isoformat())
    status = strategy_groups.challenge_daily_status(now=now)
    assert status["target_usd"] == 2.0
    assert status["pnl_today"] == 3.0
    assert status["hit"] is True


def test_challenge_daily_status_miss_when_below_target(test_db):
    now = datetime.now(timezone.utc)
    _enable_strategy("champ")
    _close_trade("champ", 500, closed_at=(now - timedelta(days=3)).isoformat())
    strategy_groups.sync_group_assignments()

    _close_trade("champ", 0.5, closed_at=now.isoformat())
    status = strategy_groups.challenge_daily_status(now=now)
    assert status["pnl_today"] == 0.5
    assert status["hit"] is False


def test_challenge_recent_days_reports_no_data_honestly(test_db):
    _enable_strategy("champ")
    _close_trade("champ", 500)
    strategy_groups.sync_group_assignments()

    now = datetime.now(timezone.utc)
    days = strategy_groups.challenge_recent_days(n_days=3, now=now)
    assert len(days) == 3
    # The seeding trade happened "now" -- earlier days in the window have
    # no closed trade at all and must be reported as no-data, not $0.
    for d in days[:-1]:
        assert d["has_data"] is False
        assert d["pnl"] is None
        assert d["hit"] is False
    assert days[-1]["has_data"] is True
