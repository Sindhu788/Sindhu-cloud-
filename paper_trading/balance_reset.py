"""Safe "reset every paper book to the starting balance" operation.

Archive-not-delete: closed trades are COPIED into paper_trade_history_archive
and a snapshot row is written to paper_balance_reset_archive before anything
changes. paper_positions is never modified, so the statistics that drive the
Wilson 25-trade gate, the Evolution 100-trade gate and per-strategy win-rate
(closed_count / win_count / the closed rows themselves) stay exactly as they
were. Only the running realized-PnL total of each strategy book is zeroed (via
the existing storage.reset_paper_balance) and, if needed, initial_balance is set
to the target, so every book shows exactly `target`.

Open positions keep running. The account drawdown baseline and all safety gates
are not touched.

This function is dry-run by default (apply=False) and refuses to run against
Postgres (the Cloud database) unless allow_cloud=True is passed explicitly.
"""
import json
import uuid
from datetime import datetime, timezone

from data_engine import db_backend, storage

_ARCHIVE_SQL = (
    "CREATE TABLE IF NOT EXISTS paper_trade_history_archive AS "
    "SELECT * FROM paper_positions WHERE 1=0",
    "CREATE TABLE IF NOT EXISTS paper_balance_reset_archive ("
    "id TEXT PRIMARY KEY, reset_at TEXT NOT NULL, target_balance REAL NOT NULL, "
    "previous_initial_balance REAL, snapshot_json TEXT NOT NULL)",
)


def _snapshot(conn):
    books = conn.execute(
        "SELECT strategy_id, realized_pnl_total, closed_count, win_count FROM paper_account_state").fetchall()
    return {
        "books": [list(b) for b in books],
        "closed_trades": conn.execute("SELECT COUNT(*) FROM paper_positions WHERE status != 'open'").fetchone()[0],
        "open_positions": conn.execute("SELECT COUNT(*) FROM paper_positions WHERE status = 'open'").fetchone()[0],
        "closed_count_sum": sum(b[2] or 0 for b in books),
        "win_count_sum": sum(b[3] or 0 for b in books),
        "realized_pnl_sum": round(sum(b[1] or 0.0 for b in books), 6),
    }


def reset_to_target(target=100.0, *, apply=False, allow_cloud=False, set_initial_balance=True):
    if db_backend.IS_POSTGRES and not allow_cloud:
        raise RuntimeError("Refusing to reset a Postgres (Cloud) database without allow_cloud=True")
    from paper_trading import config as pt_config

    settings = pt_config.load()
    previous_initial = settings.get("initial_balance")
    with storage.get_conn() as conn:
        before = _snapshot(conn)
    preview = {"applied": False, "target": target, "previous_initial_balance": previous_initial, "before": before,
               "books": len(before["books"])}
    if not apply:
        return preview

    now = datetime.now(timezone.utc).isoformat()
    with storage.get_conn() as conn:
        for stmt in _ARCHIVE_SQL:
            conn.execute(stmt)
        conn.execute(
            "INSERT INTO paper_trade_history_archive SELECT * FROM paper_positions "
            "WHERE status != 'open' AND id NOT IN (SELECT id FROM paper_trade_history_archive)")
        conn.execute(
            "INSERT INTO paper_balance_reset_archive (id, reset_at, target_balance, previous_initial_balance, snapshot_json) "
            "VALUES (?, ?, ?, ?, ?)", (uuid.uuid4().hex, now, target, previous_initial, json.dumps(before)))
    storage.reset_paper_balance(now)
    if set_initial_balance and previous_initial != target:
        pt_config.update(initial_balance=target)

    with storage.get_conn() as conn:
        after = _snapshot(conn)
        archived = conn.execute("SELECT COUNT(*) FROM paper_trade_history_archive").fetchone()[0]
    settings = pt_config.load()
    book_balances = [round(settings.get("initial_balance", 0.0) + b[1], 6) for b in after["books"]]
    checks = {
        "every_book_equals_target": all(abs(v - target) < 1e-6 for v in book_balances),
        "closed_trades_unchanged": after["closed_trades"] == before["closed_trades"],
        "closed_count_unchanged": after["closed_count_sum"] == before["closed_count_sum"],
        "win_count_unchanged": after["win_count_sum"] == before["win_count_sum"],
        "open_positions_unchanged": after["open_positions"] == before["open_positions"],
        "all_closed_trades_archived": archived >= before["closed_trades"],
    }
    return {**preview, "applied": True, "after": after, "archived_rows": archived, "checks": checks,
            "ok": all(checks.values())}
