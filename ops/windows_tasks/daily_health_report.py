"""Master plan A23 (P19): daily health report for the OWNER's private Telegram chat (09:10 PKT via Task Scheduler).

Reads only public or read-only sources: Cloud /health/details (public, no secrets) and the Cloud database READ-ONLY (MAIN_WALLET tables,
scan telemetry). Without --send it only PRINTS the report (dry run). With --send it posts to the owner's private chat using the owner's
own environment variables TELEGRAM_BOT_TOKEN and OWNER_CHAT_ID (never printed). Public groups are never used.
Usage (stable venv): python ops/windows_tasks/daily_health_report.py [--send]"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

CLOUD = os.environ.get("SINDHU_CLOUD_URL", "https://sindhu-cloud-1.onrender.com")
CONN_FILE = os.environ.get("SINDHU_NEON_FILE", r"D:\sindhu\data\config\neon_runtime_connection.json")


def _db_rows(sql, params=()):
    try:
        import psycopg
        url = os.environ.get("DATABASE_URL") or json.load(open(CONN_FILE, encoding="utf-8"))["database_url"]
        with psycopg.connect(url, connect_timeout=15) as c:
            c.read_only = True
            cur = c.execute(sql, params)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception as e:
        return {"error": type(e).__name__}


def build():
    lines = [f"SINDHU daily report {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC (paper trading only)"]
    try:
        d = requests.get(CLOUD + "/health/details", timeout=90).json()
        c = d.get("candles") or {}
        lines.append(f"Cloud: up, commit {d.get('commit')}, trading {d.get('trading')}, config errors {len(d.get('config_errors') or {})}")
        lines.append(f"Data: {c.get('fresh', '?')} fresh / {c.get('stale', '?')} stale series")
        sc = d.get("self_check") or {}
        lines.append("Self-check: " + ("OK" if sc.get("ok") else f"PROBLEM {[x['name'] for x in sc.get('checks', []) if not x.get('ok')]}"))
    except Exception as e:
        lines.append(f"Cloud: NOT REACHABLE ({type(e).__name__}) -- sleeping or down")
    since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    w = _db_rows("SELECT k, v FROM wallet_state WHERE k IN ('MAIN_WALLET:cash','MAIN_WALLET:day_start_equity')")
    if isinstance(w, list) and w:
        kv = {r["k"].split(":")[1]: float(r["v"]) for r in w}
        opens = _db_rows("SELECT COUNT(*) AS n, COALESCE(SUM(notional),0) AS v FROM wallet_positions WHERE status='open'")
        n, v = (opens[0]["n"], float(opens[0]["v"])) if isinstance(opens, list) else ("?", 0.0)
        eq = kv.get("cash", 0) + v
        lines.append(f"MAIN_WALLET: equity ~${eq:.2f} (open positions at entry value), cash ${kv.get('cash', 0):.2f}, open {n}")
    else:
        lines.append("MAIN_WALLET: not created yet or database not reachable")
    scans = _db_rows("SELECT COUNT(*) AS n FROM paper_scan_log WHERE outcome = 'complete' AND completed_at >= %s", (since,))
    if isinstance(scans, list):
        lines.append(f"Complete scans in the last 24 h: {scans[0]['n']}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true")
    a = ap.parse_args()
    text = build()
    print(text)
    if a.send:
        token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("OWNER_CHAT_ID")
        if not token or not chat:
            print("NOT SENT: set TELEGRAM_BOT_TOKEN and OWNER_CHAT_ID (owner's private chat) for this Windows user first.")
            sys.exit(2)
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat, "text": text}, timeout=30)
        print("sent" if r.status_code == 200 else f"send failed HTTP {r.status_code}")


if __name__ == "__main__":
    main()
