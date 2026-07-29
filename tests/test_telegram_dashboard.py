"""Tests for Task C: the Telegram Dashboard page's data layer --
storage.list_telegram_signal_outcomes() and paper_trading/telegram_analytics.py.
Confirms win/loss is read straight off paper_positions' own real status/pnl
(the same source Paper Trading Analytics uses), never guessed, and that
win rate is gated behind the same minimum-sample-size rule used elsewhere.
"""

from data_engine import storage
from paper_trading import telegram_analytics, pattern_stats


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


def _log_signal(position_id, strategy_id="strat1", strategy_name="Test Strategy", sent_at="2026-01-01T00:00:00+00:00", success=True):
    storage.log_telegram_message(position_id, strategy_id, strategy_name, "manual", "text", success, None, sent_at)


def test_open_position_signal_shows_as_pending(test_db):
    _open_position(id="pos1")
    _log_signal("pos1")
    rows = storage.list_telegram_signal_outcomes()
    assert len(rows) == 1
    assert rows[0]["outcome"] == "pending"


def _close(position_id, exit_price, pnl, pnl_pct, exit_reason):
    storage.close_paper_position(
        position_id, exit_price, 1700000100000, pnl, pnl_pct, exit_reason,
        {}, {}, "2026-01-02T00:00:00+00:00",
    )


def test_closed_winning_position_shows_as_win(test_db):
    _open_position(id="pos2")
    _close("pos2", 110.0, 10.0, 10.0, "take_profit")
    _log_signal("pos2")
    rows = storage.list_telegram_signal_outcomes()
    assert rows[0]["outcome"] == "win"


def test_closed_losing_position_shows_as_loss(test_db):
    _open_position(id="pos3")
    _close("pos3", 90.0, -10.0, -10.0, "stop_loss")
    _log_signal("pos3")
    rows = storage.list_telegram_signal_outcomes()
    assert rows[0]["outcome"] == "loss"


def test_failed_sends_are_excluded_from_signal_log(test_db):
    _open_position(id="pos4")
    _log_signal("pos4", success=False)
    rows = storage.list_telegram_signal_outcomes()
    assert rows == []


def test_close_followup_messages_are_not_counted_as_signals(test_db):
    _open_position(id="pos5")
    storage.log_telegram_message("pos5", "strat1", "Test Strategy", "close_followup", "text", True, None, "2026-01-01T00:00:00+00:00")
    rows = storage.list_telegram_signal_outcomes()
    assert rows == []


def test_period_filtering_by_sent_at(test_db):
    _open_position(id="pos6")
    _log_signal("pos6", sent_at="2026-01-01T00:00:00+00:00")
    _open_position(id="pos7")
    _log_signal("pos7", sent_at="2026-02-01T00:00:00+00:00")
    rows = storage.list_telegram_signal_outcomes(since_iso="2026-01-15T00:00:00+00:00")
    assert len(rows) == 1
    assert rows[0]["position_id"] == "pos7"


def test_signal_period_summary_counts_and_gates_win_rate(test_db):
    _open_position(id="posA")
    _log_signal("posA")
    _open_position(id="posB")
    _close("posB", 110.0, 10.0, 10.0, "take_profit")
    _log_signal("posB")
    summary = telegram_analytics.signal_period_summary()
    assert summary["total_signals"] == 2
    assert summary["pending"] == 1
    assert summary["wins"] == 1
    assert summary["closed"] == 1
    # Only 1 closed trade -- far below MIN_SAMPLE_SIZE -- so no misleading
    # 100% win rate should ever be shown.
    assert summary["win_rate_pct"] is None
    assert summary["min_sample_size"] == pattern_stats.MIN_SAMPLE_SIZE


def test_signal_period_summary_shows_win_rate_once_sample_size_met(test_db):
    for i in range(pattern_stats.MIN_SAMPLE_SIZE):
        pid = f"win{i}"
        _open_position(id=pid, symbol="ETHUSDT")
        _close(pid, 110.0, 10.0, 10.0, "take_profit")
        _log_signal(pid, sent_at=f"2026-01-01T00:00:{i:02d}+00:00")
    summary = telegram_analytics.signal_period_summary()
    assert summary["closed"] == pattern_stats.MIN_SAMPLE_SIZE
    assert summary["win_rate_pct"] == 100.0


def test_strategy_breakdown_groups_and_sorts_by_signal_count(test_db):
    _open_position(id="s1a", strategy_id="stratA", strategy_name="Strategy A")
    _log_signal("s1a", strategy_id="stratA", strategy_name="Strategy A")
    _open_position(id="s1b", strategy_id="stratA", strategy_name="Strategy A")
    _log_signal("s1b", strategy_id="stratA", strategy_name="Strategy A")
    _open_position(id="s2a", strategy_id="stratB", strategy_name="Strategy B")
    _log_signal("s2a", strategy_id="stratB", strategy_name="Strategy B")

    breakdown = telegram_analytics.strategy_breakdown()
    assert breakdown[0]["strategy_id"] == "stratA"
    assert breakdown[0]["total_signals"] == 2
    assert breakdown[1]["strategy_id"] == "stratB"
    assert breakdown[1]["total_signals"] == 1
