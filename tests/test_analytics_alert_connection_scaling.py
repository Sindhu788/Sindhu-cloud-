"""Urgent bug fix, 2026-09-09: GET /api/paper-trading/analytics?period=all
timed out (15000ms) immediately after "Enable All for Paper Trading" was
used for the first time (100+ strategies enabled at once). Root cause:
insights.detect_alerts() -- called by paper_trading.py's
_compute_analytics() for every request -- called storage.
get_recent_paper_alert() once or twice PER STRATEGY, and each call opens a
brand-new Postgres connection (no connection pooling on the cloud runner).
With only a handful of strategies enabled this was slow but not fatal;
with 100+ it was the same class of bug already fixed for the status and
strategy-overview endpoints, just triggered by strategy COUNT rather than
request volume. storage.list_recent_paper_alert_keys() now answers the
"already alerted?" check for every strategy from ONE query.
"""
from paper_trading import insights
from data_engine import storage


def _stats(sid, **overrides):
    row = {"strategy_id": sid, "strategy_name": sid, "closed_trades": 5,
           "total_pnl": 10.0, "win_count": 4, "win_rate": 80.0}
    row.update(overrides)
    return row


def test_detect_alerts_uses_one_connection_regardless_of_strategy_count(test_db, monkeypatch):
    strategy_stats = [_stats(f"strat{i}") for i in range(50)]
    call_count = {"n": 0}
    real_get_conn = storage.get_conn

    def counting_get_conn():
        call_count["n"] += 1
        return real_get_conn()

    monkeypatch.setattr(storage, "get_conn", counting_get_conn)
    insights.detect_alerts(strategy_stats, streaks={})

    # One read (list_recent_paper_alert_keys) plus one write per strategy
    # that actually raises a NEW alert (50/50 here, since none has alerted
    # before) -- the bug this guards against was 1-2 reads PER STRATEGY on
    # top of that, so the count would have been ~100-150 instead.
    assert call_count["n"] <= 51


def test_still_raises_and_persists_a_strong_performance_alert(test_db):
    strategy_stats = [_stats("strat1")]
    raised = insights.detect_alerts(strategy_stats, streaks={})

    assert len(raised) == 1
    assert raised[0]["alert_type"] == "strong_performance"
    assert raised[0]["strategy_id"] == "strat1"
    alerts = storage.list_paper_alerts()
    assert any(a["alert_type"] == "strong_performance" and a["strategy_id"] == "strat1" for a in alerts)


def test_does_not_reraise_within_the_dedupe_window(test_db):
    strategy_stats = [_stats("strat1")]
    first = insights.detect_alerts(strategy_stats, streaks={})
    second = insights.detect_alerts(strategy_stats, streaks={})

    assert len(first) == 1
    assert len(second) == 0


def test_raises_drawdown_alert_from_a_loss_streak(test_db):
    strategy_stats = [_stats("strat1", win_rate=20.0, total_pnl=-5.0)]
    streaks = {"strat1": {"type": "loss", "count": 3}}

    raised = insights.detect_alerts(strategy_stats, streaks=streaks)

    assert len(raised) == 1
    assert raised[0]["alert_type"] == "drawdown"


def test_does_not_cross_contaminate_alert_types_within_one_call(test_db):
    """A strategy hitting BOTH conditions in the same call must raise
    both -- the in-memory recent_keys.add() bookkeeping must key on
    (alert_type, strategy_id), not strategy_id alone."""
    strategy_stats = [_stats("strat1", win_rate=80.0, total_pnl=10.0)]
    streaks = {"strat1": {"type": "loss", "count": 3}}

    raised = insights.detect_alerts(strategy_stats, streaks=streaks)

    assert {r["alert_type"] for r in raised} == {"strong_performance", "drawdown"}
