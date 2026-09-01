"""Paper Trading time-period breakdown + honest Telegram delivery reporting.

What these tests pin down:
  - The rolling windows (Last 7 / 15 Days, Last 1 Month) really are rolling
    and really do include today, and the older calendar week/month buckets
    still behave as they always did.
  - A single strategy's period breakdown counts only that strategy's own
    trades, and never folds open positions into closed-trade counts.
  - Every Telegram delivery status is derived from what was actually
    recorded -- most importantly, that a signal is NEVER reported as
    "Sent" unless a real successful send exists for it, and that "Queued"
    is only used when a re-check will genuinely happen.
"""

from datetime import datetime, timedelta, timezone

import pytest

from data_engine import storage
from paper_trading import telegram_delivery as td
from sindhu_web.api import paper_trading as pt_api


def _now():
    return datetime.now(timezone.utc)


def _iso(days_ago=0, hours_ago=0):
    return (_now() - timedelta(days=days_ago, hours=hours_ago)).isoformat()


def _open(pos_id, strategy_id="s1", symbol="BTCUSDT", created_at=None, name="Test Strategy"):
    storage.open_paper_position({
        "id": pos_id, "exchange": "binance", "symbol": symbol, "direction": "long",
        "entry_price": 100.0, "stop_loss": 95.0, "take_profit": 110.0, "size": 1.0,
        "risk_amount": 5.0, "entry_time": int(_now().timestamp() * 1000),
        "created_at": created_at or _iso(), "strategy_id": strategy_id,
        "strategy_name": name, "confidence": 70.0,
    })


def _close(pos_id, pnl, closed_at=None, strategy_id="s1"):
    storage.close_paper_position(
        pos_id, exit_price=100.0 + pnl, exit_time=int(_now().timestamp() * 1000),
        pnl=pnl, pnl_pct=pnl, exit_reason="take_profit", lifecycle={}, reflection={},
        closed_at=closed_at or _iso(), book_key=strategy_id,
    )


# --------------------------------------------------------------- periods

def test_rolling_windows_include_today_and_reach_back_n_minus_one_days():
    """"Last 7 days" means today plus the six before it -- not today plus
    seven more, which would quietly be an 8-day window."""
    today_start = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    for period, days in (("7d", 7), ("15d", 15), ("30d", 30)):
        since, until = pt_api._period_bounds(period)
        assert until is None, f"{period} should be open-ended (runs up to now)"
        expected = (today_start - timedelta(days=days - 1)).isoformat()
        assert since == expected, period


def test_all_time_is_unbounded_and_yesterday_is_a_closed_bucket():
    assert pt_api._period_bounds("all") == (None, None)
    since, until = pt_api._period_bounds("yesterday")
    # Yesterday must END where today begins, otherwise today's trades leak
    # into it and the two periods double-count.
    today_start = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    assert until == today_start.isoformat()
    assert since == (today_start - timedelta(days=1)).isoformat()


def test_calendar_week_and_month_still_behave_as_before():
    """The Project Status page still uses these, so they must not change."""
    today_start = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    week_since, _ = pt_api._period_bounds("week")
    assert week_since == (today_start - timedelta(days=today_start.weekday())).isoformat()
    month_since, _ = pt_api._period_bounds("month")
    assert month_since == today_start.replace(day=1).isoformat()


def test_unknown_period_falls_back_to_all_time_rather_than_crashing():
    assert pt_api._period_bounds("not-a-real-period") == (None, None)


def test_strategy_period_stats_are_scoped_to_that_strategy_only(test_db):
    _close_at = _iso(hours_ago=1)
    _open("a1", strategy_id="s1")
    _close("a1", pnl=10.0, closed_at=_close_at, strategy_id="s1")
    _open("b1", strategy_id="s2")
    _close("b1", pnl=-99.0, closed_at=_close_at, strategy_id="s2")

    s1 = storage.get_paper_strategy_period_stats("s1")
    assert s1["closed_trades"] == 1
    assert s1["total_pnl"] == 10.0, "another strategy's loss must not bleed in"
    assert s1["win_count"] == 1 and s1["loss_count"] == 0
    assert s1["win_rate"] == 100.0


def test_open_positions_are_never_counted_as_closed_trades(test_db):
    _open("closed1", strategy_id="s1")
    _close("closed1", pnl=5.0, closed_at=_iso(hours_ago=1), strategy_id="s1")
    _open("stillopen", strategy_id="s1")

    stats = storage.get_paper_strategy_period_stats("s1")
    assert stats["closed_trades"] == 1, "an open position is not a finished trade"
    assert stats["open_positions"] == 1
    assert stats["win_count"] + stats["loss_count"] + stats["breakeven_count"] == 1


def test_breakeven_trade_is_not_reported_as_a_loss(test_db):
    _open("be", strategy_id="s1")
    _close("be", pnl=0.0, closed_at=_iso(hours_ago=1), strategy_id="s1")
    stats = storage.get_paper_strategy_period_stats("s1")
    assert stats["loss_count"] == 0
    assert stats["win_count"] == 0
    assert stats["breakeven_count"] == 1


def test_period_filter_excludes_trades_closed_outside_the_window(test_db):
    _open("old", strategy_id="s1")
    _close("old", pnl=100.0, closed_at=_iso(days_ago=40), strategy_id="s1")
    _open("recent", strategy_id="s1")
    _close("recent", pnl=1.0, closed_at=_iso(hours_ago=2), strategy_id="s1")

    since, until = pt_api._period_bounds("7d")
    recent_only = storage.get_paper_strategy_period_stats("s1", since, until)
    assert recent_only["closed_trades"] == 1
    assert recent_only["total_pnl"] == 1.0

    all_time = storage.get_paper_strategy_period_stats("s1")
    assert all_time["closed_trades"] == 2


# ------------------------------------------------- telegram delivery status

@pytest.mark.parametrize("error,expected", [
    ("signal is 933 minutes old (limit 15 minutes) -- too stale to send", "withheld_stale"),
    ("live price (1.2) has moved more than 0.5% away from the entry price (1.1)", "withheld_drift"),
    ("Telegram sending is turned off (master switch)", "withheld_switch"),
    ("rate limit reached for this hour", "withheld_rate_limit"),
    ("Telegram bot token or channel ID not configured yet", "not_configured"),
    ("failed after 3 attempts: ConnectionError(ProtocolError('Connection aborted.'))", "blocked_network"),
    ("failed after 3 attempts: ProxyError(MaxRetryError(...))", "blocked_network"),
    ('ReadTimeout(ReadTimeoutError("HTTPSConnectionPool(host=api.telegram.org)"))', "blocked_network"),
    ("Bad Request: chat not found", "failed_telegram"),
])
def test_every_real_failure_shape_classifies_correctly(error, expected):
    assert td.classify_attempt({"success": 0, "error": error}) == expected


def test_a_successful_attempt_is_the_only_thing_that_reports_as_sent():
    assert td.classify_attempt({"success": 1, "error": None}) == "sent"


def test_signal_is_only_ever_sent_when_a_real_success_exists():
    """The whole point of this module: nothing gets to claim delivery
    without a recorded successful send behind it."""
    never_attempted = {"status": "open", "attempts": []}
    assert td.classify_signal(never_attempted, auto_send_enabled=True) != "sent"
    assert td.classify_signal(never_attempted, auto_send_enabled=False) != "sent"

    only_failures = {"status": "closed", "attempts": [
        {"success": 0, "error": "failed after 3 attempts: ConnectionError(x)"},
    ]}
    assert td.classify_signal(only_failures, auto_send_enabled=True) == "blocked_network"


def test_an_eventual_success_counts_as_sent_despite_earlier_failures():
    signal = {"status": "closed", "attempts": [
        {"success": 1, "error": None},
        {"success": 0, "error": "failed after 3 attempts: ConnectionError(x)"},
    ]}
    assert td.classify_signal(signal, auto_send_enabled=False) == "sent"


def test_queued_is_only_claimed_when_a_recheck_will_genuinely_happen():
    """"Queued" must be a true statement. The hourly sweep only re-checks
    positions that are still OPEN, and only when auto-send is on."""
    still_open = {"status": "open", "attempts": []}
    assert td.classify_signal(still_open, auto_send_enabled=True) == "queued"
    # Auto-send off: nothing will ever pick it up again.
    assert td.classify_signal(still_open, auto_send_enabled=False) == "never_sent"
    # Already closed: the sweep skips closed positions entirely.
    closed = {"status": "closed", "attempts": []}
    assert td.classify_signal(closed, auto_send_enabled=True) == "never_sent"


def test_outcome_of_an_open_trade_is_pending_never_a_guess():
    rows = td.delivery_rows([
        {"id": "x", "status": "open", "pnl": None, "attempts": []},
    ], auto_send_enabled=False)
    assert rows[0]["outcome"] == "pending"


def test_delivery_summary_counts_and_win_rate(test_db):
    rows = td.delivery_rows([
        {"id": "1", "status": "closed", "pnl": 5.0, "attempts": [{"success": 1, "error": None}]},
        {"id": "2", "status": "closed", "pnl": -2.0, "attempts": [
            {"success": 0, "error": "signal is 40 minutes old (limit 15 minutes) -- too stale to send"}]},
        {"id": "3", "status": "closed", "pnl": 1.0, "attempts": [
            {"success": 0, "error": "failed after 3 attempts: ConnectionError(x)"}]},
        {"id": "4", "status": "open", "pnl": None, "attempts": []},
    ], auto_send_enabled=True)
    summary = td.delivery_summary(rows)

    assert summary["total_generated"] == 4
    assert summary["delivered"] == 1
    assert summary["withheld"] == 1
    assert summary["failed"] == 1
    assert summary["queued"] == 1
    assert summary["closed_trades"] == 3
    assert summary["outcomes"]["win"] == 2 and summary["outcomes"]["loss"] == 1
    assert summary["win_rate_pct"] == pytest.approx(66.7, abs=0.1)


def test_win_rate_is_none_not_zero_when_nothing_has_finished():
    """0% would read as "every one of them lost", which is a different and
    false claim than "nothing has finished yet"."""
    rows = td.delivery_rows([
        {"id": "1", "status": "open", "pnl": None, "attempts": []},
    ], auto_send_enabled=True)
    assert td.delivery_summary(rows)["win_rate_pct"] is None


def test_generated_signals_query_includes_signals_that_were_never_attempted(test_db):
    """Driving off paper_positions rather than telegram_message_log is the
    entire reason this reporting is honest -- a log-driven query would
    return nothing here while the system had really generated two signals."""
    _open("g1", strategy_id="s1", created_at=_iso(hours_ago=2))
    _open("g2", strategy_id="s1", created_at=_iso(hours_ago=1))

    signals = storage.list_generated_signals_with_delivery()
    assert len(signals) == 2
    assert all(s["attempts"] == [] for s in signals)
    # Newest first.
    assert signals[0]["id"] == "g2"

    rows = td.delivery_rows(signals, auto_send_enabled=False)
    assert {r["delivery_status"] for r in rows} == {"never_sent"}
    assert td.delivery_summary(rows)["delivered"] == 0


def test_generated_signals_attach_their_real_delivery_attempts(test_db):
    _open("g1", strategy_id="s1")
    storage.log_telegram_message(
        "g1", "s1", "Test Strategy", "manual", "some text",
        success=False, error="failed after 3 attempts: ConnectionError(x)", now_iso=_iso(),
    )
    signals = storage.list_generated_signals_with_delivery()
    assert len(signals[0]["attempts"]) == 1
    rows = td.delivery_rows(signals, auto_send_enabled=True)
    assert rows[0]["delivery_status"] == "blocked_network"
    assert rows[0]["delivery_label"] == "Failed -- network blocked"
    # The verbatim recorded reason survives to the screen.
    assert "ConnectionError" in rows[0]["delivery_detail"]


def test_every_status_id_has_a_human_label():
    for status in td.STATUS_LABELS:
        assert td.STATUS_LABELS[status], status
    # Nothing in the classifier can produce a status the label map lacks.
    produced = {
        td.classify_attempt({"success": 0, "error": e})
        for e in ("too stale", "moved more than", "master switch", "rate limit",
                  "not configured", "ConnectionError", "anything else")
    } | {"sent", "queued", "never_sent"}
    assert produced <= set(td.STATUS_LABELS)
