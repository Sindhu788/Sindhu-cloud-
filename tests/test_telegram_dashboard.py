"""Tests for Task C: the Telegram Dashboard page's data layer --
storage.list_telegram_signal_outcomes() and paper_trading/telegram_analytics.py.
Confirms win/loss is read straight off paper_positions' own real status/pnl
(the same source Paper Trading Analytics uses), never guessed, and that
win rate is gated behind the same minimum-sample-size rule used elsewhere.
"""

import pytest

from data_engine import config as base_config, storage
from paper_trading import telegram_analytics, pattern_stats


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


def test_signal_period_summary_totals_real_pnl_not_hypothetical(test_db):
    """Part 5 (Telegram-specific analytics): the real dollar PnL of
    Telegram-sent, closed trades -- distinct from hypothetical_pnl()'s
    rescaled $100-account figure below."""
    _open_position(id="posC1")
    _close("posC1", 110.0, 10.0, 10.0, "take_profit")
    _log_signal("posC1")
    _open_position(id="posC2")
    _close("posC2", 90.0, -4.0, -4.0, "stop_loss")
    _log_signal("posC2")
    _open_position(id="posC3")  # still open -- must not contribute
    _log_signal("posC3")

    summary = telegram_analytics.signal_period_summary()
    assert summary["total_pnl"] == 6.0


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


def test_strategy_breakdown_counts_losses_correctly(test_db):
    """Regression test (Batch 6, Task 5): entry[r["outcome"]] used to index
    the per-strategy dict with the outcome string directly ("win"/"loss"),
    but the dict's keys are "wins"/"losses" (plural) -- "breakeven" and
    "pending" happen to match their own outcome string, which is why this
    went unnoticed until a real loss was ever counted, at which point it
    raised a KeyError instead of incrementing anything."""
    _open_position(id="l1", strategy_id="stratC", strategy_name="Strategy C")
    _close("l1", 90.0, -10.0, -10.0, "stop_loss")
    _log_signal("l1", strategy_id="stratC", strategy_name="Strategy C")

    breakdown = telegram_analytics.strategy_breakdown()
    row = next(e for e in breakdown if e["strategy_id"] == "stratC")
    assert row["losses"] == 1
    assert row["closed"] == 1


def test_strategy_breakdown_tracks_real_total_pnl_per_strategy(test_db):
    _open_position(id="p1", strategy_id="stratD", strategy_name="Strategy D")
    _close("p1", 110.0, 10.0, 10.0, "take_profit")
    _log_signal("p1", strategy_id="stratD", strategy_name="Strategy D")
    _open_position(id="p2", strategy_id="stratD", strategy_name="Strategy D")
    _close("p2", 95.0, -3.0, -3.0, "stop_loss")
    _log_signal("p2", strategy_id="stratD", strategy_name="Strategy D")

    breakdown = telegram_analytics.strategy_breakdown()
    row = next(e for e in breakdown if e["strategy_id"] == "stratD")
    assert row["total_pnl"] == 7.0


# --------------------------------------------------------------- Part 5: best-performing sent-signal strategy

def test_best_performing_strategy_picks_the_highest_real_total_pnl(test_db):
    _open_position(id="bp1", strategy_id="stratWinner", strategy_name="Winner")
    _close("bp1", 120.0, 20.0, 20.0, "take_profit")
    _log_signal("bp1", strategy_id="stratWinner", strategy_name="Winner")

    _open_position(id="bp2", strategy_id="stratLoser", strategy_name="Loser")
    _close("bp2", 90.0, -5.0, -5.0, "stop_loss")
    _log_signal("bp2", strategy_id="stratLoser", strategy_name="Loser")

    best = telegram_analytics.best_performing_strategy()
    assert best["strategy_id"] == "stratWinner"
    assert best["total_pnl"] == 20.0


def test_best_performing_strategy_ignores_all_pending_strategies(test_db):
    _open_position(id="bp3", strategy_id="stratPending", strategy_name="Pending")
    _log_signal("bp3", strategy_id="stratPending", strategy_name="Pending")

    assert telegram_analytics.best_performing_strategy() is None


def test_best_performing_strategy_none_with_no_signals_at_all(test_db):
    assert telegram_analytics.best_performing_strategy() is None


# --------------------------------------------------------------- Hypothetical $100/month PnL tracker

def test_hypothetical_pnl_scales_real_r_multiple_onto_hypothetical_capital(test_db):
    # risk_amount=5.0 (default), pnl=+10.0 -> R-multiple = 2.0.
    # Default risk_pct_default=1.0% on $100 hypothetical capital = $1 risked
    # per trade -> hypothetical pnl for this trade = 2.0 * $1 = $2.00.
    _open_position(id="posW")
    _close("posW", 110.0, 10.0, 10.0, "take_profit")
    _log_signal("posW")

    result = telegram_analytics.hypothetical_pnl()
    assert result["hypothetical_capital"] == 100.0
    assert result["risk_pct_used"] == 1.0
    assert result["counted_trades"] == 1
    assert result["hypothetical_pnl"] == 2.0
    assert result["hypothetical_balance"] == 102.0


def test_hypothetical_pnl_only_counts_closed_trades(test_db):
    _open_position(id="posOpen")
    _log_signal("posOpen")  # still open -- must not contribute
    result = telegram_analytics.hypothetical_pnl()
    assert result["counted_trades"] == 0
    assert result["hypothetical_pnl"] == 0.0
    assert result["hypothetical_balance"] == 100.0


def test_hypothetical_pnl_combines_win_and_loss_r_multiples(test_db):
    _open_position(id="posW2", risk_amount=5.0)
    _close("posW2", 110.0, 10.0, 10.0, "take_profit")  # R = +2.0
    _log_signal("posW2")

    _open_position(id="posL2", risk_amount=5.0)
    _close("posL2", 95.0, -5.0, -5.0, "stop_loss")  # R = -1.0
    _log_signal("posL2")

    result = telegram_analytics.hypothetical_pnl()
    # (2.0 + -1.0) R * $1 hypothetical risk per trade = $1.00
    assert result["counted_trades"] == 2
    assert result["hypothetical_pnl"] == 1.0


def test_hypothetical_pnl_respects_configured_risk_pct(test_db):
    from paper_trading import config as pt_config
    pt_config.save({**pt_config.load(), "risk_pct_default": 2.0})

    _open_position(id="posW3")
    _close("posW3", 110.0, 10.0, 10.0, "take_profit")  # R = +2.0
    _log_signal("posW3")

    # 2% of $100 = $2 risked per trade -> 2.0 R * $2 = $4.00
    result = telegram_analytics.hypothetical_pnl()
    assert result["risk_pct_used"] == 2.0
    assert result["hypothetical_pnl"] == 4.0
