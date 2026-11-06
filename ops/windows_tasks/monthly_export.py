"""Master plan A23 (P45): monthly CSV export of MAIN_WALLET and research trades, READ-ONLY from the Cloud database, into
D:\\sindhu_runtime\\exports\\YYYY-MM\\ (default: the previous calendar month). Never modifies anything; an existing file is kept.
Usage (stable venv): python ops/windows_tasks/monthly_export.py [--month 2026-10]"""
import argparse
import csv
import json
import os
from datetime import datetime, timedelta, timezone

CONN_FILE = os.environ.get("SINDHU_NEON_FILE", r"D:\sindhu\data\config\neon_runtime_connection.json")
OUT = os.environ.get("SINDHU_EXPORT_DIR", r"D:\sindhu_runtime\exports")
QUERIES = {
    "wallet_positions": "SELECT * FROM wallet_positions WHERE opened_at >= %s AND opened_at < %s ORDER BY opened_at",
    "wallet_journal": "SELECT * FROM wallet_journal WHERE created_at >= %s AND created_at < %s ORDER BY created_at",
    "research_positions": "SELECT * FROM paper_positions WHERE status = 'closed' AND closed_at >= %s AND closed_at < %s",
}


def month_bounds(month):
    y, m = map(int, month.split("-"))
    return f"{y:04d}-{m:02d}-01", f"{y + (m == 12):04d}-{(m % 12) + 1:02d}-01"


def main():
    now = datetime.now(timezone.utc)
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", default=(now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m"))
    a = ap.parse_args()
    start, end = month_bounds(a.month)
    folder = os.path.join(OUT, a.month)
    os.makedirs(folder, exist_ok=True)
    import psycopg
    url = os.environ.get("DATABASE_URL") or json.load(open(CONN_FILE, encoding="utf-8"))["database_url"]
    with psycopg.connect(url, connect_timeout=15) as c:
        c.read_only = True
        for name, sql in QUERIES.items():
            path = os.path.join(folder, f"{name}.csv")
            if os.path.exists(path):
                print(f"{name}: already exported, kept")
                continue
            try:
                cur = c.execute(sql, (start, end))
            except Exception as e:
                print(f"{name}: skipped ({type(e).__name__})")
                c.rollback()
                continue
            rows = cur.fetchall()
            with open(path + ".tmp", "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow([d[0] for d in cur.description])
                w.writerows(rows)
            os.replace(path + ".tmp", path)
            print(f"{name}: {len(rows)} rows -> {path}")


if __name__ == "__main__":
    main()
