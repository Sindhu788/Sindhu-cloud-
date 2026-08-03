"""Batch 7, Task 5: Daily Honest Report -- paper_trading/daily_report.py.
Confirms every figure is read straight from real storage (paper_positions,
telegram_message_log, paper_trading.insights' streak detector), each
"no data yet" case says so plainly instead of a bare zero, the report
never sends when the Telegram master switch is off, and it never sends
twice in the same calendar day.
"""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from data_engine import config as base_config, storage
from paper_trading import daily_report, telegram_bot


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


NOW = datetime(2026, 3, 15, 18, 0, 0, tzinfo=timezone.utc)


def _open_position(**overrides):
    pos = {
        "id": "pos1", "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": 1700000000000, "created_at": "2026-03-15T08:00:00+00:00",
        "strategy_id": "strat1", "strategy_name": "Test Strategy",
    }
    pos.update(overrides)
    storage.open_paper_position(pos)
    return pos


def _close(position_id, exit_price, pnl, pnl_pct, exit_reason, closed_at):
    storage.close_paper_position(position_id, exit_price, 1700000100000, pnl, pnl_pct, exit_reason, {}, {}, closed_at)


def _log_send(trigger_type="manual", success=True, sent_at="2026-03-15T09:00:00+00:00", high=False, position_id="pos1"):
    text = "some signal text" + (" ⭐ HIGH CONFIDENCE SIGNAL ⭐" if high else "")
    storage.log_telegram_message(position_id, "strat1", "Test Strategy", trigger_type, text, success, None, sent_at)


# ------------------------------------------------------------- generate_daily_report

def test_no_data_anywhere_says_so_plainly(test_db):
    report = daily_report.generate_daily_report(now=NOW)
    assert "koi signal Telegram par nahi bheja gaya" in report["report_text"]
    assert "koi trade band nahi hua" in report["report_text"]
    assert "koi strategy losing streak par nahi hai" in report["report_text"]
    assert report["signals_sent_today"] == 0
    assert report["today_closed_trades"] == 0


def test_counts_signals_by_tier_correctly(test_db):
    _log_send(sent_at="2026-03-15T09:00:00+00:00", high=True)
    _log_send(sent_at="2026-03-15T10:00:00+00:00", high=False)
    _log_send(sent_at="2026-03-15T11:00:00+00:00", high=False)
    report = daily_report.generate_daily_report(now=NOW)
    assert report["signals_sent_today"] == 3
    assert report["high_confidence_count"] == 1
    assert report["low_tier_count"] == 2
    assert "3 signal(s)" in report["report_text"]


def test_excludes_failed_sends_and_yesterdays_sends(test_db):
    _log_send(sent_at="2026-03-15T09:00:00+00:00", success=False)  # failed -- excluded
    _log_send(sent_at="2026-03-14T23:00:00+00:00")  # yesterday -- excluded
    _log_send(sent_at="2026-03-15T09:30:00+00:00")  # today, real -- counted
    report = daily_report.generate_daily_report(now=NOW)
    assert report["signals_sent_today"] == 1


def test_todays_closed_trades_and_pnl(test_db):
    _open_position(id="p1")
    _close("p1", 110.0, 10.0, 10.0, "take_profit", "2026-03-15T09:00:00+00:00")
    _open_position(id="p2")
    _close("p2", 90.0, -5.0, -5.0, "stop_loss", "2026-03-15T10:00:00+00:00")
    report = daily_report.generate_daily_report(now=NOW)
    assert report["today_closed_trades"] == 2
    assert report["today_wins"] == 1
    assert report["today_pnl"] == 5.0
    assert "aaj ka PnL: $5.00" in report["report_text"]


def test_month_to_date_includes_trades_from_earlier_in_the_month(test_db):
    _open_position(id="p1")
    _close("p1", 110.0, 20.0, 20.0, "take_profit", "2026-03-02T09:00:00+00:00")  # earlier this month
    _open_position(id="p2")
    _close("p2", 110.0, 5.0, 5.0, "take_profit", "2026-03-15T09:00:00+00:00")  # today
    report = daily_report.generate_daily_report(now=NOW)
    assert report["month_to_date_pnl"] == 25.0
    assert report["month_to_date_closed_trades"] == 2


def test_best_strategy_today_is_the_highest_pnl_one(test_db):
    _open_position(id="p1", strategy_id="stratA", strategy_name="Strategy A")
    _close("p1", 110.0, 50.0, 50.0, "take_profit", "2026-03-15T09:00:00+00:00")
    _open_position(id="p2", strategy_id="stratB", strategy_name="Strategy B")
    _close("p2", 105.0, 5.0, 5.0, "take_profit", "2026-03-15T09:00:00+00:00")
    report = daily_report.generate_daily_report(now=NOW)
    assert report["best_strategy_today"]["strategy_id"] == "stratA"
    assert "Strategy A" in report["report_text"]


def test_no_profitable_strategy_today_says_so(test_db):
    _open_position(id="p1", strategy_id="stratA", strategy_name="Strategy A")
    _close("p1", 90.0, -10.0, -10.0, "stop_loss", "2026-03-15T09:00:00+00:00")
    report = daily_report.generate_daily_report(now=NOW)
    assert "koi strategy profit mein nahi hai" in report["report_text"]


def test_flags_a_real_losing_streak(test_db):
    for i in range(3):
        pid = f"p{i}"
        _open_position(id=pid, strategy_id="stratC", strategy_name="Strategy C",
                        created_at=f"2026-03-15T0{i}:00:00+00:00")
        _close(pid, 90.0, -5.0, -5.0, "stop_loss", f"2026-03-15T0{i}:30:00+00:00")
    report = daily_report.generate_daily_report(now=NOW)
    assert len(report["losing_streaks"]) == 1
    assert report["losing_streaks"][0]["strategy_id"] == "stratC"
    assert report["losing_streaks"][0]["count"] == 3
    assert "Strategy C" in report["report_text"]


def test_short_losing_streak_below_threshold_is_not_flagged(test_db):
    for i in range(2):  # below MIN_LOSING_STREAK_TO_FLAG (3)
        pid = f"p{i}"
        _open_position(id=pid, strategy_id="stratD", strategy_name="Strategy D",
                        created_at=f"2026-03-15T0{i}:00:00+00:00")
        _close(pid, 90.0, -5.0, -5.0, "stop_loss", f"2026-03-15T0{i}:30:00+00:00")
    report = daily_report.generate_daily_report(now=NOW)
    assert report["losing_streaks"] == []


# ------------------------------------------------------------- maybe_send_daily_report

def test_does_not_send_when_master_switch_is_off(test_db):
    telegram_bot.save_settings(bot_token="x", channel_id="y", master_send_enabled=False)
    with patch.object(telegram_bot, "_raw_send") as mock_send:
        result = daily_report.maybe_send_daily_report(now=NOW)
    assert result is None
    mock_send.assert_not_called()


def test_sends_once_when_master_switch_is_on(test_db):
    telegram_bot.save_settings(bot_token="x", channel_id="y", master_send_enabled=True)
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        result = daily_report.maybe_send_daily_report(now=NOW)
    assert result["ok"] is True
    mock_send.assert_called_once()
    sent_text = mock_send.call_args[0][0]
    assert "Roz Ki Report" in sent_text


def test_never_sends_twice_in_the_same_calendar_day(test_db):
    telegram_bot.save_settings(bot_token="x", channel_id="y", master_send_enabled=True)
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        first = daily_report.maybe_send_daily_report(now=NOW)
        second = daily_report.maybe_send_daily_report(now=NOW.replace(hour=23))
    assert first is not None
    assert second is None
    mock_send.assert_called_once()


def test_sends_again_on_a_new_calendar_day(test_db):
    telegram_bot.save_settings(bot_token="x", channel_id="y", master_send_enabled=True)
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        daily_report.maybe_send_daily_report(now=NOW)
        daily_report.maybe_send_daily_report(now=NOW.replace(day=16))
    assert mock_send.call_count == 2
