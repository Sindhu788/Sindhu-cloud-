"""Strategy Lab: a weekly, honest check for a genuinely profitable
strategy. These tests specifically confirm the honest "nothing found yet"
case works (not just the success case), that a losing/weak strategy is
never picked just to have something to show, and that approval only ever
happens for the exact strategy a scan actually found qualifying -- never
automatically."""

from datetime import datetime, timedelta, timezone

import pytest

from data_engine import storage
from paper_trading import strategy_lab


def _iso(days_ago=0):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _open_position(pos_id, strategy_id, strategy_name):
    storage.open_paper_position({
        "id": pos_id, "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": 1700000000000, "created_at": _iso(10),
        "strategy_id": strategy_id, "strategy_name": strategy_name,
    })


def _close(pos_id, pnl):
    storage.close_paper_position(pos_id, 100.0, 1700000100000, pnl, pnl, "take_profit", {}, {}, _iso(1))


def _make_trades(strategy_id, strategy_name, count, win_count, pnl_each_win, pnl_each_loss):
    for i in range(count):
        pos_id = f"{strategy_id}_pos{i}"
        _open_position(pos_id, strategy_id, strategy_name)
        _close(pos_id, pnl_each_win if i < win_count else pnl_each_loss)


# ------------------------------------------------------------- honest no-result case

def test_no_qualifying_strategy_reports_honestly(test_db):
    # A strategy with real trades but a losing record -- must never be
    # picked as "best" just to have something to show.
    _make_trades("strat_losing", "Losing Strategy", count=30, win_count=10, pnl_each_win=5.0, pnl_each_loss=-10.0)

    scan = strategy_lab.scan_for_profitable_strategy()

    assert scan["qualifying_strategy_id"] is None
    assert scan["qualifying_strategy_name"] is None
    assert scan["strategies_checked"] == 1


def test_no_strategies_at_all_reports_honestly(test_db):
    scan = strategy_lab.scan_for_profitable_strategy()
    assert scan["qualifying_strategy_id"] is None
    assert scan["strategies_checked"] == 0


def test_too_few_trades_does_not_qualify_even_if_profitable(test_db):
    # Profitable and high win rate, but not enough real trades yet.
    _make_trades("strat_new", "New Strategy", count=5, win_count=5, pnl_each_win=10.0, pnl_each_loss=0.0)

    scan = strategy_lab.scan_for_profitable_strategy()
    assert scan["qualifying_strategy_id"] is None


def test_high_win_rate_but_net_loss_does_not_qualify(test_db):
    # 60% win rate but the losses are bigger than the wins -- net negative
    # after cost, so this must NOT qualify despite the flattering win rate.
    _make_trades("strat_bigloss", "Big Loss Strategy", count=30, win_count=18, pnl_each_win=1.0, pnl_each_loss=-5.0)

    scan = strategy_lab.scan_for_profitable_strategy()
    assert scan["qualifying_strategy_id"] is None


# ------------------------------------------------------------- qualifying case

def test_genuinely_profitable_strategy_is_found(test_db):
    _make_trades("strat_good", "Good Strategy", count=30, win_count=20, pnl_each_win=10.0, pnl_each_loss=-5.0)

    scan = strategy_lab.scan_for_profitable_strategy()

    assert scan["qualifying_strategy_id"] == "strat_good"
    assert scan["qualifying_strategy_name"] == "Good Strategy"
    assert scan["qualifying_trade_count"] == 30
    assert scan["qualifying_win_rate"] == pytest.approx(66.67, abs=0.1)
    assert scan["qualifying_pnl"] == pytest.approx(20 * 10.0 + 10 * -5.0)
    assert scan["approved"] is False


def test_best_of_multiple_qualifiers_is_picked_by_highest_pnl(test_db):
    _make_trades("strat_a", "Strategy A", count=30, win_count=20, pnl_each_win=10.0, pnl_each_loss=-5.0)  # net 150
    _make_trades("strat_b", "Strategy B", count=30, win_count=20, pnl_each_win=20.0, pnl_each_loss=-5.0)  # net 350

    scan = strategy_lab.scan_for_profitable_strategy()
    assert scan["qualifying_strategy_id"] == "strat_b"


def test_scan_is_persisted_and_retrievable(test_db):
    strategy_lab.scan_for_profitable_strategy()
    latest = storage.get_latest_strategy_lab_scan()
    assert latest is not None
    assert latest["strategies_checked"] == 0


# ------------------------------------------------------------- approval gate

def test_approve_enables_paper_trading_and_telegram_override(test_db):
    _make_trades("strat_good", "Good Strategy", count=30, win_count=20, pnl_each_win=10.0, pnl_each_loss=-5.0)
    scan = strategy_lab.scan_for_profitable_strategy()

    result = strategy_lab.approve_candidate(scan["id"], "strat_good")

    assert result["approved"] is True
    configs = storage.list_paper_strategy_configs()
    assert configs["strat_good"]["enabled"] is True
    override = storage.get_paper_strategy_override("strat_good")
    assert override["manual_alert"] is True


def test_approve_rejects_a_strategy_that_did_not_qualify(test_db):
    _make_trades("strat_good", "Good Strategy", count=30, win_count=20, pnl_each_win=10.0, pnl_each_loss=-5.0)
    _make_trades("strat_losing", "Losing Strategy", count=30, win_count=10, pnl_each_win=5.0, pnl_each_loss=-10.0)
    scan = strategy_lab.scan_for_profitable_strategy()

    with pytest.raises(strategy_lab.ApprovalError):
        strategy_lab.approve_candidate(scan["id"], "strat_losing")


def test_approve_rejects_when_no_strategy_qualified(test_db):
    _make_trades("strat_losing", "Losing Strategy", count=30, win_count=10, pnl_each_win=5.0, pnl_each_loss=-10.0)
    scan = strategy_lab.scan_for_profitable_strategy()

    with pytest.raises(strategy_lab.ApprovalError):
        strategy_lab.approve_candidate(scan["id"], "strat_losing")


def test_approve_rejects_stale_scan_id(test_db):
    _make_trades("strat_good", "Good Strategy", count=30, win_count=20, pnl_each_win=10.0, pnl_each_loss=-5.0)
    scan = strategy_lab.scan_for_profitable_strategy()
    stale_id = scan["id"]
    strategy_lab.scan_for_profitable_strategy()  # a newer scan now exists

    with pytest.raises(strategy_lab.ApprovalError):
        strategy_lab.approve_candidate(stale_id, "strat_good")


def test_approve_is_never_called_by_the_scan_itself(test_db):
    _make_trades("strat_good", "Good Strategy", count=30, win_count=20, pnl_each_win=10.0, pnl_each_loss=-5.0)
    scan = strategy_lab.scan_for_profitable_strategy()

    assert scan["approved"] is False
    configs = storage.list_paper_strategy_configs()
    assert "strat_good" not in configs or not configs["strat_good"]["enabled"]


# ------------------------------------------------------------- scheduler gate

def test_maybe_run_skips_if_scanned_recently(test_db):
    strategy_lab.scan_for_profitable_strategy()
    first_count = len(storage.list_strategy_lab_scans())

    result = strategy_lab.maybe_run_strategy_lab_scan()

    assert result is None
    assert len(storage.list_strategy_lab_scans()) == first_count


def test_maybe_run_respects_master_feature_toggle(test_db, monkeypatch):
    from data_engine import feature_toggles
    monkeypatch.setattr(feature_toggles, "is_enabled", lambda key: False)

    result = strategy_lab.maybe_run_strategy_lab_scan()
    assert result is None
    assert storage.get_latest_strategy_lab_scan() is None
