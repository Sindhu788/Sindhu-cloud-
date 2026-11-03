import pytest

from data_engine import db_backend, storage
from paper_trading import balance_reset, config as pt_config


def _seed(test_db):
    with storage.get_conn() as c:
        c.execute("INSERT INTO paper_account_state (strategy_id, realized_pnl_total, closed_count, win_count, updated_at) "
                  "VALUES ('s1', -40.0, 30, 9, 'x'), ('s2', 5.5, 12, 7, 'x')")
        for i, (sid, st) in enumerate([("s1", "closed"), ("s1", "closed"), ("s2", "closed"), ("s2", "open")]):
            c.execute("INSERT INTO paper_positions (exchange, symbol, direction, entry_price, stop_loss, take_profit, size, "
                      "risk_amount, entry_time, strategy_id, status, pnl, created_at) VALUES ('bybit','BTCUSDT','long',1,0.9,1.2,1,1,?,?,?,?,'2026-01-01')",
                      (1000 + i, sid, st, -1.0 if st == "closed" else None))


def test_dry_run_changes_nothing(test_db):
    _seed(test_db)
    out = balance_reset.reset_to_target(100.0)
    assert out["applied"] is False and out["before"]["closed_trades"] == 3
    with storage.get_conn() as c:
        assert c.execute("SELECT realized_pnl_total FROM paper_account_state WHERE strategy_id='s1'").fetchone()[0] == -40.0


def test_apply_archives_trades_keeps_gate_counters_and_sets_every_book_to_target(test_db, monkeypatch, tmp_path):
    from data_engine import paths
    monkeypatch.setattr(paths, "CONFIG_DIR", str(tmp_path))
    _seed(test_db)
    out = balance_reset.reset_to_target(100.0, apply=True)
    assert out["ok"], out["checks"]
    assert out["archived_rows"] == 3
    with storage.get_conn() as c:
        assert c.execute("SELECT COUNT(*) FROM paper_positions").fetchone()[0] == 4          # nothing deleted
        assert tuple(c.execute("SELECT SUM(closed_count), SUM(win_count) FROM paper_account_state").fetchone()) == (42, 16)
        assert c.execute("SELECT COUNT(*) FROM paper_balance_reset_archive").fetchone()[0] == 1
    assert pt_config.load()["initial_balance"] == 100.0
    again = balance_reset.reset_to_target(100.0, apply=True)   # idempotent archive
    assert again["archived_rows"] == 3 and again["ok"]


def test_refuses_postgres_without_explicit_flag(monkeypatch):
    monkeypatch.setattr(db_backend, "IS_POSTGRES", True)
    with pytest.raises(RuntimeError):
        balance_reset.reset_to_target(100.0, apply=True)
