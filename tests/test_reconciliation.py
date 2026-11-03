from datetime import datetime, timezone

from data_engine import storage
from paper_trading import monitoring, reconciliation as rc


def _seed(c, state_pnl, closed=2, wins=1):
    c.execute("INSERT INTO paper_account_state (strategy_id, realized_pnl_total, closed_count, win_count, updated_at) VALUES ('s1', ?, ?, ?, 'x')",
              (state_pnl, closed, wins))
    for i, pnl in enumerate((2.5, -1.0)):
        c.execute("INSERT INTO paper_positions (exchange, symbol, direction, entry_price, stop_loss, take_profit, size, risk_amount, entry_time, "
                  "strategy_id, status, pnl, created_at) VALUES ('okx','BTCUSDT','long',1,0.9,1.2,1,1,?,'s1','closed',?,'2026-01-01')", (1000 + i, pnl))
    c.execute("INSERT INTO paper_strategy_groups (strategy_id, group_key, assigned_at, auto_assigned) VALUES ('s1','profitable','x',1)")


def test_matching_books_reconcile_clean(test_db):
    with storage.get_conn() as c:
        _seed(c, 1.5)
        res = rc.run(c)
    assert res["ok"] and res["books_checked"] == 1 and res["groups"]["profitable"]["diff"] == 0
    assert "OK" in rc.summary_line(res)


def test_a_cent_of_drift_or_wrong_counters_is_caught(test_db):
    with storage.get_conn() as c:
        _seed(c, 1.6, closed=3, wins=2)
        res = rc.run(c)
    assert not res["ok"] and res["mismatches"][0]["pnl_diff"] == 0.1 and res["mismatches"][0]["stored_closed"] == 3
    assert "MISMATCH" in rc.summary_line(res)


def test_open_trades_do_not_count_and_alert_goes_to_owner_once_a_day(test_db):
    with storage.get_conn() as c:
        _seed(c, 9.0)
    sent = []
    lim = monitoring.Limiter()
    now = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
    res = rc.maybe_alert(send=lambda t: sent.append(t) or True, limiter=lim, now=now)
    assert res["ok"] is False and len(sent) == 1 and sent[0].startswith("[SINDHU monitor] ALERT")
    assert rc.maybe_alert(send=lambda t: sent.append(t) or True, limiter=lim, now=now) is None and len(sent) == 1
