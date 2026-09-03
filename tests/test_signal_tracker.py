"""Tests for Batch 6, Task 5: paper_trading/signal_tracker.py -- the Live
Signal Tracker feed and the Backtest/Paper/Telegram win-rate match table.
Confirms every number is read straight from real storage (paper_positions,
telegram_message_log, backtest_batches/backtest_results), never guessed,
and that divergence is only ever flagged once both sides being compared
have enough closed trades to trust (the same MIN_SAMPLE_SIZE floor used
throughout this system).
"""

from unittest.mock import patch

import pytest

from data_engine import config as base_config, storage
from paper_trading import signal_tracker, pattern_stats


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _open_position(**overrides):
    pos = {
        "id": "pos1", "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": 1700000000000, "created_at": "2026-01-01T00:00:00+00:00",
        "strategy_id": "strat1", "strategy_name": "Test Strategy",
    }
    pos.update(overrides)
    storage.open_paper_position(pos)
    return pos


def _close(position_id, exit_price, pnl, pnl_pct, exit_reason, closed_at="2026-01-02T00:00:00+00:00"):
    storage.close_paper_position(
        position_id, exit_price, 1700000100000, pnl, pnl_pct, exit_reason, {}, {}, closed_at,
    )


def _log_signal(position_id, strategy_id="strat1", strategy_name="Test Strategy", sent_at="2026-01-01T00:00:00+00:00", success=True):
    storage.log_telegram_message(position_id, strategy_id, strategy_name, "manual", "text", success, None, sent_at)


def _make_completed_batch(batch_id, strategy_name, total_trades, wins, final_balance=1100.0, initial_balance=1000.0):
    storage.create_batch(batch_id, strategy_name, "binance", {"initial_balance": initial_balance}, "2026-01-01T00:00:00+00:00")
    storage.save_result(
        batch_id, "BTCUSDT", "1h", "completed",
        {"total_trades": total_trades, "wins": wins, "final_balance": final_balance,
         "profit_pct": 10.0, "max_drawdown_pct": 5.0},
        "2026-01-01T00:00:00+00:00",
    )
    storage.update_batch_status(batch_id, "completed", "2026-01-01T00:00:00+00:00")


# ------------------------------------------------------------- live feed

def test_live_signal_feed_reports_real_outcomes(test_db):
    _open_position(id="p1")
    _log_signal("p1")
    _open_position(id="p2")
    _close("p2", 110.0, 10.0, 10.0, "take_profit")
    _log_signal("p2")

    feed = signal_tracker.live_signal_feed()
    assert feed["total_signals"] == 2
    assert feed["pending"] == 1
    assert feed["wins"] == 1
    assert feed["closed"] == 1
    # below MIN_SAMPLE_SIZE -- must not show a misleading win rate
    assert feed["win_rate_pct"] is None
    outcomes = {r["position_id"]: r["outcome"] for r in feed["signals"]}
    assert outcomes == {"p1": "pending", "p2": "win"}


def test_live_signal_feed_gates_win_rate_at_min_sample_size(test_db):
    for i in range(pattern_stats.MIN_SAMPLE_SIZE):
        pid = f"win{i}"
        _open_position(id=pid)
        _close(pid, 110.0, 10.0, 10.0, "take_profit")
        _log_signal(pid, sent_at=f"2026-01-01T00:00:{i:02d}+00:00")
    feed = signal_tracker.live_signal_feed()
    assert feed["closed"] == pattern_stats.MIN_SAMPLE_SIZE
    assert feed["win_rate_pct"] == 100.0


def test_live_signal_feed_respects_limit_but_not_summary_counts(test_db):
    for i in range(5):
        pid = f"p{i}"
        _open_position(id=pid)
        _log_signal(pid, sent_at=f"2026-01-01T00:00:{i:02d}+00:00")
    feed = signal_tracker.live_signal_feed(limit=2)
    assert len(feed["signals"]) == 2
    assert feed["total_signals"] == 5  # summary counts the full set, not just the returned page


# ------------------------------------------------------------- match table

def test_match_table_includes_backtest_paper_and_telegram_win_rates(test_db):
    _make_completed_batch("b1", "Test Strategy", total_trades=10, wins=7)  # 70%
    for i in range(3):
        pid = f"pt{i}"
        _open_position(id=pid, strategy_id="strat1", strategy_name="Test Strategy")
        _close(pid, 110.0, 10.0, 10.0, "take_profit", closed_at=f"2026-01-02T00:00:{i:02d}+00:00")
        _log_signal(pid, sent_at=f"2026-01-01T00:00:{i:02d}+00:00")

    table = signal_tracker.strategy_match_table()
    row = next(r for r in table["strategies"] if r["strategy_id"] == "strat1")
    assert row["backtest_win_rate"] == 70.0
    assert row["backtest_batch_id"] == "b1"
    assert row["paper_win_rate"] == 100.0
    assert row["paper_closed_trades"] == 3
    # only 3 closed trades -- far below MIN_SAMPLE_SIZE -- telegram win
    # rate must not be shown as a misleadingly confident number
    assert row["telegram_win_rate"] is None
    assert row["diverges"] is False


def test_match_table_has_no_backtest_row_when_no_completed_batch_matches(test_db):
    _open_position(id="p1", strategy_id="strat9", strategy_name="Never Backtested")
    _close("p1", 110.0, 10.0, 10.0, "take_profit")
    _log_signal("p1", strategy_id="strat9", strategy_name="Never Backtested")

    table = signal_tracker.strategy_match_table()
    row = next(r for r in table["strategies"] if r["strategy_id"] == "strat9")
    assert row["backtest_win_rate"] is None
    assert row["backtest_batch_id"] is None


def test_match_table_survives_a_database_with_no_backtest_tables(test_db):
    """Part 7 (this task, cloud nav audit): the cloud runner's own curated
    Postgres schema deliberately excludes backtest_batches/backtest_results
    (see data_engine/db_backend.py) -- this page must degrade to "no
    backtest data available" for that strategy instead of a 500, so it's
    safe to link from the cloud nav."""
    _open_position(id="p1", strategy_id="strat10", strategy_name="Cloud Strategy")
    _close("p1", 110.0, 10.0, 10.0, "take_profit")
    _log_signal("p1", strategy_id="strat10", strategy_name="Cloud Strategy")

    with patch.object(storage, "latest_completed_batch_for_strategy_name",
                       side_effect=Exception('relation "backtest_batches" does not exist')):
        table = signal_tracker.strategy_match_table()

    row = next(r for r in table["strategies"] if r["strategy_id"] == "strat10")
    assert row["backtest_win_rate"] is None
    assert row["backtest_batch_id"] is None


def test_match_table_flags_real_divergence_between_paper_and_telegram_win_rates(test_db):
    """Paper trading (ALL trades for this strategy) wins half the time;
    the Telegram-signaled SUBSET wins almost none of the time -- a real,
    material divergence (the confluence/Wilson gating that decides what
    gets signaled isn't tracking with what actually wins) that should be
    flagged once both sides clear MIN_SAMPLE_SIZE."""
    n = pattern_stats.MIN_SAMPLE_SIZE
    # n trades signaled to telegram, almost all losses
    for i in range(n):
        pid = f"tg{i}"
        won = i == 0
        _open_position(id=pid, strategy_id="stratD", strategy_name="Divergent Strategy")
        _close(pid, 110.0 if won else 90.0, 10.0 if won else -10.0, 10.0 if won else -10.0,
               "take_profit" if won else "stop_loss", closed_at=f"2026-01-02T00:{i:02d}:00+00:00")
        _log_signal(pid, strategy_id="stratD", strategy_name="Divergent Strategy",
                     sent_at=f"2026-01-01T00:{i:02d}:00+00:00")
    # n more trades for the SAME strategy that were never signaled, mostly wins,
    # so the overall paper win rate ends up far above the telegram-only win rate.
    for i in range(n):
        pid = f"nosig{i}"
        won = i < n - 1
        _open_position(id=pid, strategy_id="stratD", strategy_name="Divergent Strategy")
        _close(pid, 110.0 if won else 90.0, 10.0 if won else -10.0, 10.0 if won else -10.0,
               "take_profit" if won else "stop_loss", closed_at=f"2026-01-03T00:{i:02d}:00+00:00")

    table = signal_tracker.strategy_match_table()
    row = next(r for r in table["strategies"] if r["strategy_id"] == "stratD")
    assert row["paper_closed_trades"] == 2 * n
    assert row["telegram_closed_trades"] == n
    assert row["paper_win_rate"] is not None and row["telegram_win_rate"] is not None
    assert abs(row["paper_win_rate"] - row["telegram_win_rate"]) >= signal_tracker.DIVERGENCE_THRESHOLD_PCT
    assert row["diverges"] is True


def test_match_table_read_only_never_modifies_underlying_tables(test_db):
    _make_completed_batch("b1", "Test Strategy", total_trades=10, wins=7)
    _open_position(id="p1")
    _log_signal("p1")
    before_positions = storage.list_telegram_signal_outcomes()
    before_batches = storage.list_recent_batches()
    signal_tracker.strategy_match_table()
    signal_tracker.live_signal_feed()
    assert storage.list_telegram_signal_outcomes() == before_positions
    assert storage.list_recent_batches() == before_batches
