"""Daily accounting reconciliation (read-only): do the stored balances agree with the trades?

For every paper book (strategy):   realized_pnl_total (paper_account_state)  ==  sum(pnl) of its closed trades (paper_positions)
                                   closed_count                              ==  number of closed trades
                                   win_count                                 ==  closed trades with pnl > 0
Balance of a book = initial_balance + realized_pnl_total, so a PnL match means balance == start + sum(closed P&L).
Trade P&L is stored net of the modelled commission/slippage (fees are inside `pnl`), so "minus fees as modelled" holds when the
two sides agree. Also totals per group. Any difference above the tolerance is reported; the owner is alerted (owner chat only).
"""
TOLERANCE = 0.01   # one cent of paper money


def run(conn, tolerance=TOLERANCE):
    books = {r[0]: (float(r[1] or 0.0), int(r[2] or 0), int(r[3] or 0))
             for r in conn.execute("SELECT strategy_id, realized_pnl_total, closed_count, win_count FROM paper_account_state").fetchall()}
    trades = {}
    for sid, pnl in conn.execute("SELECT COALESCE(strategy_id,'__lessons__'), pnl FROM paper_positions WHERE status != 'open' AND pnl IS NOT NULL").fetchall():
        t = trades.setdefault(sid, [0.0, 0, 0])
        t[0] += float(pnl); t[1] += 1; t[2] += 1 if float(pnl) > 0 else 0
    groups = dict(conn.execute("SELECT strategy_id, group_key FROM paper_strategy_groups").fetchall())
    # A balance reset zeroes realized_pnl_total but keeps every trade; paper_balance_resets records the PnL that was zeroed.
    # So the expected stored value is: sum(closed trade PnL) - sum(PnL zeroed by earlier resets).
    zeroed = {}
    try:
        for sid, prev in conn.execute("SELECT strategy_id, previous_realized_pnl_total FROM paper_balance_resets").fetchall():
            zeroed[sid] = zeroed.get(sid, 0.0) + float(prev or 0.0)
    except Exception:
        zeroed = {}
    mismatches, per_group = [], {}
    for sid in sorted(set(books) | set(trades)):
        stored = books.get(sid, (0.0, 0, 0))
        real = trades.get(sid, [0.0, 0, 0])
        expected = real[0] - zeroed.get(sid, 0.0)
        d_pnl = round(stored[0] - expected, 4)
        if abs(d_pnl) > tolerance or stored[1] != real[1] or stored[2] != real[2]:
            mismatches.append({"strategy_id": sid, "group": groups.get(sid), "stored_pnl": round(stored[0], 4), "trades_pnl": round(real[0], 4), "zeroed_by_resets": round(zeroed.get(sid, 0.0), 4),
                               "pnl_diff": d_pnl, "stored_closed": stored[1], "trade_closed": real[1], "stored_wins": stored[2], "trade_wins": real[2]})
        g = per_group.setdefault(groups.get(sid) or "unclassified", [0.0, 0.0])
        g[0] += stored[0]; g[1] += expected
    group_rows = {k: {"stored_pnl": round(v[0], 2), "trades_pnl": round(v[1], 2), "diff": round(v[0] - v[1], 4)} for k, v in per_group.items()}
    return {"ok": not mismatches, "books_checked": len(set(books) | set(trades)), "mismatches": mismatches, "groups": group_rows,
            "total_stored_pnl": round(sum(b[0] for b in books.values()), 2), "total_trades_pnl": round(sum(t[0] for t in trades.values()) - sum(zeroed.values()), 2)}


def summary_line(result):
    if result["ok"]:
        return f"Reconciliation OK: {result['books_checked']} books, stored PnL {result['total_stored_pnl']} == trades PnL {result['total_trades_pnl']}."
    worst = sorted(result["mismatches"], key=lambda m: -abs(m["pnl_diff"]))[:2]
    return (f"Reconciliation MISMATCH in {len(result['mismatches'])} of {result['books_checked']} books "
            f"(stored {result['total_stored_pnl']} vs trades {result['total_trades_pnl']}). Worst: "
            + "; ".join(f"{m['strategy_id']} diff {m['pnl_diff']}" for m in worst))


def maybe_alert(send=None, limiter=None, now=None):
    """Once per UTC day: run the check and alert the owner chat ONLY on a mismatch. Returns the result or None if already run."""
    from datetime import datetime, timezone
    from data_engine import storage
    from paper_trading import monitoring
    now = now or datetime.now(timezone.utc)
    limiter = limiter or monitoring._limiter or monitoring._persistent_limiter()
    code = "reconcile:" + now.strftime("%Y-%m-%d")
    if not limiter.allow(code, 24 * 60):
        return None
    with storage.get_conn() as c:
        result = run(c)
    limiter.mark(code)
    if not result["ok"] and limiter.allow("reconciliation_mismatch", 24 * 60):
        if (send or monitoring._owner_send)("[SINDHU monitor] ALERT: " + summary_line(result)):
            limiter.mark("reconciliation_mismatch")
    return result
