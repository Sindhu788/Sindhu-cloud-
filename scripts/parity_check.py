"""Read-only Local vs Cloud parity report (Markdown to stdout). Cloud = Neon (connection string from the local file
data/config/neon_runtime_connection.json, never printed), Local = D:/sindhu SQLite opened read-only + config files.
Secrets are reported as booleans only. Usage: python scripts/parity_check.py [data_dir]"""
import json, os, sqlite3, sys

sys.stdout.reconfigure(encoding="utf-8")
DATA = sys.argv[1] if len(sys.argv) > 1 else "D:/sindhu/data"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def jload(path, default=None):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default if default is not None else {}


def main():
    import psycopg
    from paper_trading import reconciliation
    url = jload(os.path.join(DATA, "config", "neon_runtime_connection.json")).get("database_url")
    cloud = psycopg.connect(url, connect_timeout=30, options="-c default_transaction_read_only=on")
    local = sqlite3.connect("file:" + os.path.join(DATA, "database", "sindhu.db") + "?mode=ro", uri=True, timeout=60)

    def norm(v):
        from decimal import Decimal
        return round(float(v), 2) if isinstance(v, (Decimal, float)) else v

    def q(conn, sql):
        cur = conn.cursor(); cur.execute(sql); return [tuple(norm(x) for x in r) for r in cur.fetchall()]

    def both(sql):
        return q(local, sql), q(cloud, sql)

    rows = []

    def add(item, l, c, note=""):
        rows.append((item, l, c, "yes" if str(l) == str(c) else ("by design" if note.startswith("by design") else "NO"), note))

    l, c = both("SELECT COUNT(*) FROM paper_strategy_config WHERE enabled=1")
    l2, c2 = both("SELECT COUNT(*) FROM paper_strategy_config WHERE enabled=1 AND COALESCE(paused,0)=0")
    add("Enabled strategies", l[0][0], c[0][0]); add("Enabled and not paused", l2[0][0], c2[0][0])
    l, c = both("SELECT group_key, COUNT(*) FROM paper_strategy_groups GROUP BY group_key ORDER BY group_key")
    add("Groups (key:count)", dict(l), dict(c))
    l, c = both("SELECT COUNT(*), ROUND(CAST(COALESCE(SUM(pnl),0) AS NUMERIC),2) FROM paper_positions WHERE status!='open' AND pnl IS NOT NULL")
    add("Closed trades / total P&L (history kept)", tuple(l[0]), tuple(c[0]), "by design: Cloud keeps trading after the 3 Nov copy, Local is frozen; difference = trades closed on Cloud since")
    l, c = both("SELECT COUNT(*), ROUND(CAST(COALESCE(SUM(realized_pnl_total),0) AS NUMERIC),2), COALESCE(SUM(closed_count),0), COALESCE(SUM(win_count),0) FROM paper_account_state")
    add("Books / realized P&L since reset / closed counter / wins counter", tuple(l[0]), tuple(c[0]), "by design: counters (closed, wins) stay across the $100 reset; Cloud has new trades since, Local is frozen")
    l, c = both("SELECT COUNT(*) FROM paper_trade_history_archive")
    add("Archive of trades before the $100 reset", l[0][0], c[0][0], "archive intact = no data deleted")
    l, c = both("SELECT COUNT(*) FROM paper_positions WHERE status='open'")
    add("Open positions", l[0][0], c[0][0], "by design: local engine is off, Cloud trades live")

    ls = jload(os.path.join(DATA, "config", "paper_trading_settings.json"))
    cs = {}
    try:
        cur = cloud.cursor(); cur.execute("SELECT value_json FROM cloud_settings WHERE key='paper_trading_settings'"); r = cur.fetchone()
        cs = r[0] if isinstance(r[0], dict) else json.loads(r[0])
    except Exception:
        pass
    for k in ("initial_balance", "coin_filter_mode", "coin_filter_top_n", "engine_enabled", "dry_run", "risk_pct", "lookback_days", "tick_interval_seconds"):
        add(f"paper setting {k}", ls.get(k, "(default)"), cs.get(k, "(default)"), "by design: local engine runs in safe mode" if k == "engine_enabled" else "")
    from paper_trading import telegram_bot
    _TG_DEFAULTS = dict(telegram_bot._DEFAULTS)
    lt = jload(os.path.join(DATA, "config", "telegram_settings.json"))
    ct = {}
    try:
        cur = cloud.cursor(); cur.execute("SELECT value_json FROM cloud_settings WHERE key='telegram_settings'"); r = cur.fetchone()
        ct = r[0] if isinstance(r[0], dict) else json.loads(r[0])
    except Exception:
        pass
    for k in ("channel_group_filter", "auto_send_enabled", "auto_send_high_confidence_only", "signal_freshness_minutes", "signal_price_drift_pct",
              "auto_send_min_confluence_ratio", "rate_limit_per_hour", "silent_hours_enabled"):
        dflt = _TG_DEFAULTS.get(k, "(default)")     # a key missing from the stored settings means the code default applies
        add(f"telegram {k}", lt.get(k, dflt), ct.get(k, dflt), "owner decision pending" if k == "auto_send_high_confidence_only" else "")
    add("telegram master_send_enabled", lt.get("master_send_enabled"), ct.get("master_send_enabled"), "by design: Cloud is the single publisher")
    for k in ("bot_token", "channel_id", "personal_chat_id", "proxy_url"):
        note = {"bot_token": "by design: Local must NOT have a token (Cloud's comes from the Render env var, not visible here)",
                "channel_id": "by design: Local must NOT have a channel (Cloud's comes from the Render env var)",
                "proxy_url": "by design: Local uses a proxy for Telegram tests; Cloud needs none"}.get(k, "")
        add(f"telegram {k} set?", bool(lt.get(k)), bool(ct.get(k)), note)

    print("| Item | Local | Cloud | Match | Note |\n|---|---|---|---|---|")
    for it, a, b, m, n in rows:
        print(f"| {it} | {a} | {b} | {m} | {n} |")
    print("\nReconciliation (stored P&L vs closed trades, tolerance 0.01):")
    for name, conn in (("Local", local), ("Cloud", cloud)):
        res = reconciliation.run(conn)
        print(f"- {name}: {reconciliation.summary_line(res)}")
    # balance check: every book should be initial_balance + realized after the reset
    init = float(cs.get("initial_balance") or 0) or None
    cur = cloud.cursor(); cur.execute("SELECT MIN(realized_pnl_total), MAX(realized_pnl_total), COUNT(*) FROM paper_account_state"); mn, mx, n = cur.fetchone()
    print(f"- Cloud books: {n}, realized since reset min {mn:.2f} / max {mx:.2f}; initial balance setting {init}")
    cur = local.cursor(); cur.execute("SELECT MIN(realized_pnl_total), MAX(realized_pnl_total), COUNT(*) FROM paper_account_state"); mn, mx, n = cur.fetchone()
    print(f"- Local books: {n}, realized since reset min {mn:.2f} / max {mx:.2f}; initial balance setting {ls.get('initial_balance')}")


if __name__ == "__main__":
    main()
