"""One-off maintenance script (not part of the app): archives ALL current
Paper Trading data (per-strategy running PnL/win-count totals, and every
position ever opened) to a timestamped JSON file, closes out any
positions still marked "open" with a neutral (0 PnL) administrative
close so nothing is left dangling with no engine managing it, then
resets the running per-strategy counters to zero and records a
"fresh session" marker.

Deliberately does NOT touch paper_trading/*.py (the decision-making
engine) or the database schema -- this is a data lifecycle operation
only, using the same storage.close_paper_position() data-layer function
the engine itself uses for a real trade close (with pnl=0 and a
clearly-labeled exit_reason so it's never mistaken for a real market
exit), not any engine/strategy logic.

Historical trade rows in paper_positions are NEVER deleted -- they stay
in the database, in full, forever, for audit. Only the two ROLLING
AGGREGATE tables (paper_account_state, paper_strategy_performance) are
reset, since those are what the dashboard reads as "current" PnL/win-rate
and are exactly what would otherwise keep blending pre-fix and post-fix
results together.

Usage: python scripts/archive_and_reset_paper_trading.py
"""
import sys
import os
import json
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_engine import storage, paths
from data_engine import config as base_config

ARCHIVE_REASON = (
    "Paper Trading data collected before the engine-verification work "
    "(entry-condition/duplicate-clause bugs, timeframe-role bugs, the "
    "Automatic Strategy Safety Check, the Self-Correcting Import Pipeline, "
    "and Walk-Forward Testing) is not reliable evidence of these strategies' "
    "real performance -- several of the strategies that traded in this "
    "archived window (e.g. Fabio Valentina's Models) are confirmed to have "
    "been running under rules that have since been found broken and fixed. "
    "Archived, not deleted, so it remains available for audit."
)


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def main():
    now = _now_iso()
    with storage.get_conn() as conn:
        account_state = [dict(zip(
            ["strategy_id", "realized_pnl_total", "closed_count", "win_count", "updated_at"], r))
            for r in conn.execute(
                "SELECT strategy_id, realized_pnl_total, closed_count, win_count, updated_at "
                "FROM paper_account_state").fetchall()]
        strategy_performance = [dict(zip(
            ["strategy_id", "strategy_name", "trades", "wins", "losses", "total_pnl", "avg_rr", "score", "updated_at"], r))
            for r in conn.execute(
                "SELECT strategy_id, strategy_name, trades, wins, losses, total_pnl, avg_rr, score, updated_at "
                "FROM paper_strategy_performance").fetchall()]
        all_positions = [dict(zip(
            ["id", "exchange", "symbol", "direction", "entry_price", "exit_price", "stop_loss", "take_profit",
             "size", "risk_amount", "entry_time", "exit_time", "pnl", "pnl_pct", "exit_reason", "entry_reason",
             "strategy_id", "strategy_name", "strategy_version", "status", "created_at", "closed_at"], r))
            for r in conn.execute(
                "SELECT id, exchange, symbol, direction, entry_price, exit_price, stop_loss, take_profit, "
                "size, risk_amount, entry_time, exit_time, pnl, pnl_pct, exit_reason, entry_reason, "
                "strategy_id, strategy_name, strategy_version, status, created_at, closed_at "
                "FROM paper_positions").fetchall()]

    open_positions = [p for p in all_positions if p["status"] == "open"]
    closed_positions = [p for p in all_positions if p["status"] == "closed"]

    print(f"Archiving: {len(account_state)} account_state rows, {len(strategy_performance)} "
          f"strategy_performance rows, {len(all_positions)} positions "
          f"({len(open_positions)} open, {len(closed_positions)} closed)", flush=True)

    archive = {
        "archived_at": now, "reason": ARCHIVE_REASON,
        "paper_account_state": account_state,
        "paper_strategy_performance": strategy_performance,
        "paper_positions": all_positions,
    }
    os.makedirs(paths.HISTORY_DIR, exist_ok=True)
    archive_filename = f"paper_trading_legacy_archive_{now.replace(':', '-')}.json"
    archive_path = os.path.join(paths.HISTORY_DIR, archive_filename)
    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(archive, f, indent=2, default=str)
    print(f"Archive written to {archive_path}", flush=True)

    # Close out anything still "open" -- the engine that was managing them
    # is not running, so nothing is currently deciding their exits. A
    # neutral (0 pnl) administrative close, clearly labeled, is used
    # instead of fabricating a market exit price/outcome that never
    # actually happened.
    for pos in open_positions:
        storage.close_paper_position(
            pos["id"], exit_price=pos["entry_price"], exit_time=int(datetime.now(timezone.utc).timestamp() * 1000),
            pnl=0.0, pnl_pct=0.0, exit_reason="archived_legacy_shutdown",
            lifecycle={"note": "administratively closed during Paper Trading reset -- no real market exit"},
            reflection={}, closed_at=now, book_key=pos["strategy_id"],
        )
    print(f"Administratively closed {len(open_positions)} stale open position(s) (0 PnL, clearly labeled).", flush=True)

    # Reset the ROLLING AGGREGATES only -- paper_positions rows above are
    # never touched/deleted, they remain in full for audit.
    with storage.get_conn() as conn:
        conn.execute("UPDATE paper_account_state SET realized_pnl_total=0, closed_count=0, win_count=0, updated_at=?", (now,))
        conn.execute("UPDATE paper_strategy_performance SET trades=0, wins=0, losses=0, total_pnl=0, avg_rr=NULL, score=NULL, updated_at=?", (now,))
    print("Reset paper_account_state and paper_strategy_performance to zero for every strategy.", flush=True)

    base_config.save_config("paper_trading_session.json", {
        "fresh_session_started_at": now,
        "reason": "Reset after Backtesting Engine verification work (safety check, self-correction, walk-forward).",
        "legacy_archive_file": archive_filename,
        "legacy_positions_archived": len(all_positions),
        "legacy_open_positions_closed": len(open_positions),
    })
    print(f"Recorded fresh-session marker: fresh_session_started_at={now}", flush=True)


if __name__ == "__main__":
    main()
