from datetime import datetime, timedelta, timezone

from data_engine import storage
from paper_trading import go_live


def _add(c, pnls, start):
    for i, pnl in enumerate(pnls):
        t = int((start + timedelta(hours=i * 6)).timestamp() * 1000)
        c.execute("INSERT INTO paper_positions (exchange, symbol, direction, entry_price, stop_loss, take_profit, size, risk_amount, entry_time, exit_time, "
                  "strategy_id, status, pnl, created_at) VALUES ('okx','BTCUSDT','long',1,0.9,1.2,1,1,?,?,'s','closed',?,'2026-01-01')", (t, t, pnl))


def _by_name(gates):
    return {g["gate"].split(" (")[0]: g for g in gates}


def test_no_fresh_trades_means_no_data_not_a_pass(test_db):
    with storage.get_conn() as c:
        g = _by_name(go_live.evaluate(c))
    assert g["Continuous paper days on fresh live data"]["status"] == "NO DATA"
    assert g["Closed trades on fresh data"]["status"] == "NO DATA"
    assert all(x["status"] != "PASS" for x in g.values() if x["gate"].startswith(("Continuous", "Closed", "Profit", "Max")))


def test_a_good_record_passes_and_a_bad_one_fails(test_db):
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    with storage.get_conn() as c:
        _add(c, [2.0, -1.0] * 120, start)          # 240 trades over 60 days, PF 2.0, tiny drawdown
        g = _by_name(go_live.evaluate(c, now=start + timedelta(days=70)))
    assert g["Continuous paper days on fresh live data"]["status"] == "PASS"
    assert g["Closed trades on fresh data"]["status"] == "PASS"
    assert g["Profit factor after fees/slippage"]["status"] == "PASS"
    assert g["Max drawdown"]["status"] == "PASS"
    # losing record
    with storage.get_conn() as c:
        c.execute("DELETE FROM paper_positions")
        _add(c, [-1.0, 0.5] * 120, start)
        g = _by_name(go_live.evaluate(c, now=start + timedelta(days=70)))
    assert g["Profit factor after fees/slippage"]["status"] == "FAIL" and g["Max drawdown"]["status"] == "FAIL"


def test_manual_gates_are_never_auto_passed(test_db):
    with storage.get_conn() as c:
        gates = go_live.evaluate(c)
    manual = [g for g in gates if g["status"] == "MANUAL"]
    assert len(manual) == 4 and "Always-on paid hosting (no sleep)" in {g["gate"] for g in manual}
    assert "Gate" in go_live.render_markdown(gates)
