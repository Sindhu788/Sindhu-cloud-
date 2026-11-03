"""Go-live readiness gates (paper-only system; this is NOT financial advice and does not enable real trading).

Each gate is measurable. `evaluate(conn)` returns the current value, the threshold and PASS / FAIL / MANUAL / NO DATA.
Thresholds live here and in docs/GO_LIVE_CRITERIA.md - keep them identical.
"""
from datetime import datetime, timedelta, timezone

FRESH_DATA_CUTOFF = "2026-09-17"      # confidence recalibration + legacy engine on live data
START_BALANCE = 100.0
THRESHOLDS = {
    "min_days": 28, "min_trades": 200, "min_pf_net": 1.3, "max_drawdown_pct": 20.0,
    "max_stale_rate_pct": 1.0, "min_uptime_pct": 99.0,
}


def _dt(v):
    try:
        if isinstance(v, (int, float)) or str(v).isdigit():
            return datetime.fromtimestamp(float(v) / 1000.0, tz=timezone.utc)
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return None


def evaluate(conn, now=None):
    now = now or datetime.now(timezone.utc)
    cut = datetime.fromisoformat(FRESH_DATA_CUTOFF).replace(tzinfo=timezone.utc)
    rows = conn.execute("SELECT entry_time, exit_time, pnl FROM paper_positions WHERE status != 'open' AND pnl IS NOT NULL").fetchall()
    trades = sorted(((_dt(r[1]) or _dt(r[0]), float(r[2])) for r in rows if (_dt(r[1]) or _dt(r[0])) and (_dt(r[1]) or _dt(r[0])) >= cut), key=lambda t: t[0])
    n = len(trades)
    days = (trades[-1][0] - trades[0][0]).days if n > 1 else 0
    wins = sum(p for _, p in trades if p > 0); losses = -sum(p for _, p in trades if p <= 0)
    pf = round(wins / losses, 2) if losses > 0 else None
    eq = peak = dd = 0.0
    for _, p in trades:
        eq += p; peak = max(peak, eq); dd = max(dd, peak - eq)
    dd_pct = round(100.0 * dd / START_BALANCE, 1)
    stale = total = 0
    try:
        since = (now - timedelta(days=7)).isoformat()
        total = conn.execute("SELECT COUNT(*) FROM paper_decision_trace WHERE ts >= ?", (since,)).fetchone()[0]
        stale = conn.execute("SELECT COUNT(*) FROM paper_decision_trace WHERE ts >= ? AND failed_gate = 'market_data'", (since,)).fetchone()[0]
    except Exception:
        pass
    stale_rate = round(100.0 * stale / total, 2) if total else None
    uptime = None
    try:
        since = (now - timedelta(days=7)).isoformat()
        hours = {r[0][:13] for r in conn.execute("SELECT started_at FROM paper_scan_log WHERE started_at >= ?", (since,)).fetchall()}
        uptime = round(100.0 * len(hours) / (7 * 24), 1) if hours else None
    except Exception:
        pass
    try:
        from paper_trading import reconciliation
        recon_ok = reconciliation.run(conn)["ok"]
    except Exception:
        recon_ok = None

    def gate(name, value, rule, ok):
        return {"gate": name, "value": value, "rule": rule, "status": "NO DATA" if value is None else ("PASS" if ok else "FAIL")}

    T = THRESHOLDS
    return [
        gate("Continuous paper days on fresh live data", days if n else None, f">= {T['min_days']} days (closed trades since {FRESH_DATA_CUTOFF})", days >= T["min_days"]),
        gate("Closed trades on fresh data", n if n else None, f">= {T['min_trades']}", n >= T["min_trades"]),
        gate("Profit factor after fees/slippage (as modelled in pnl)", pf, f">= {T['min_pf_net']}", (pf or 0) >= T["min_pf_net"]),
        gate("Max drawdown (% of $100 start)", dd_pct if n else None, f"<= {T['max_drawdown_pct']} %", dd_pct <= T["max_drawdown_pct"]),
        gate("Stale-data decisions (last 7 days)", stale_rate, f"<= {T['max_stale_rate_pct']} % of decisions", (stale_rate or 0) <= T["max_stale_rate_pct"]),
        gate("Scanner uptime (hours with a scan, last 7 days)", uptime, f">= {T['min_uptime_pct']} %", (uptime or 0) >= T["min_uptime_pct"]),
        gate("Accounting reconciliation clean", None if recon_ok is None else int(recon_ok), "balance == start + closed P&L, every book", bool(recon_ok)),
        {"gate": "Always-on paid hosting (no sleep)", "value": "manual", "rule": "paid plan or VPS; not the free plan", "status": "MANUAL"},
        {"gate": "WebSocket/stream candle feed with gap-fill", "value": "manual", "rule": "docs/LIVE_FEED_PLAN.md implemented", "status": "MANUAL"},
        {"gate": "Owner alerts + daily summary received", "value": "manual", "rule": "personal_chat_id set and a real alert seen", "status": "MANUAL"},
        {"gate": "Secrets rotated, backups restore-tested, runbook rehearsed", "value": "manual", "rule": "docs/OWNER_TODO.md sections N, K; docs/RUNBOOK.md", "status": "MANUAL"},
    ]


def render_markdown(gates):
    lines = ["| Gate | Current | Required | Status |", "|---|---|---|---|"]
    for g in gates:
        lines.append(f"| {g['gate']} | {g['value'] if g['value'] is not None else 'n/a'} | {g['rule']} | **{g['status']}** |")
    return "\n".join(lines)
