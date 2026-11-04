"""Read-only export of the Cloud Postgres to JSON Lines, one file per table, in a NEW timestamped folder (never overwrites).

  python scripts/backup_cloud_export.py [output_root]        (default output_root: D:\\sindhu_backup_phase0)

The connection string is read from the DATABASE_URL environment variable, or from data/config/neon_runtime_connection.json
(key "database_url"). It is never printed. The session is opened read-only. Skipped on purpose: auth_* tables (credentials)
and any candle/kline table. A _manifest.json with the exact row count per table is written last - restore verification uses it.
"""
import datetime
import decimal
import json
import os
import sys


def _url():
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for cand in (os.path.join(here, "data", "config", "neon_runtime_connection.json"), "D:/sindhu/data/config/neon_runtime_connection.json"):
        if os.path.exists(cand):
            return json.load(open(cand, encoding="utf-8"))["database_url"]
    raise SystemExit("No DATABASE_URL and no neon_runtime_connection.json found")


def _jsonable(o):
    if isinstance(o, (datetime.datetime, datetime.date)):
        return o.isoformat()
    if isinstance(o, decimal.Decimal):
        return float(o)
    if isinstance(o, (bytes, memoryview)):
        return bytes(o).hex()
    return str(o)


def main(root=None):
    import psycopg
    root = root or (sys.argv[1] if len(sys.argv) > 1 else "D:/sindhu_backup_phase0")
    out = os.path.join(root, "cloud_export_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
    os.makedirs(out, exist_ok=False)                      # refuses to reuse a folder
    manifest = {}
    with psycopg.connect(_url(), connect_timeout=30, options="-c default_transaction_read_only=on") as conn:
        cur = conn.cursor()
        cur.execute("select tablename from pg_tables where schemaname='public' order by 1")
        for (table,) in cur.fetchall():
            if table.startswith("auth_"):
                manifest[table] = "SKIPPED (credentials)"; continue
            if "kline" in table or "candle" in table:
                manifest[table] = "SKIPPED (candle table)"; continue
            c2 = conn.cursor()
            c2.execute(f'select count(*) from "{table}"'); expected = c2.fetchone()[0]
            c2.execute(f'select * from "{table}"')
            cols, written = [d.name for d in c2.description], 0
            with open(os.path.join(out, table + ".jsonl"), "w", encoding="utf-8") as f:
                for row in c2:
                    f.write(json.dumps(dict(zip(cols, row)), default=_jsonable) + "\n"); written += 1
            manifest[table] = [expected, written]
    json.dump(manifest, open(os.path.join(out, "_manifest.json"), "w"), indent=1)
    bad = [t for t, v in manifest.items() if isinstance(v, list) and v[0] != v[1]]
    print("export folder:", out, "| tables:", len(manifest), "| mismatched while exporting:", bad)
    return out


if __name__ == "__main__":
    main()
