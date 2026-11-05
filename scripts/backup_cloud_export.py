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


SECRET_KEY_MARKERS = ("token", "secret", "password", "passwd", "api_key", "apikey", "private_key", "credential")


def redact_row(table, cols, row):
    """Day 7 security fix: the `cloud_settings` table stores the Cloud API token and the strategy-sync secret as rows. A backup file must not hold
    them in plain text, so the VALUE of every secret-like key is replaced by a marker that keeps only the length. Row counts (used by the restore
    verification) are unchanged."""
    if table != "cloud_settings":
        return row
    d = dict(zip(cols, row))
    key = str(d.get("key", "")).lower()
    if any(m in key for m in SECRET_KEY_MARKERS):
        v = d.get("value_json")
        d["value_json"] = f"<redacted:{len(str(v))} chars>"
        return tuple(d[c] for c in cols)
    return row


def _export_table(psycopg, url, table, out, tries=3):
    """One table per fresh AUTOCOMMIT connection (no long idle transaction, which Neon's pooler terminates); written to a .tmp file and renamed only
    when complete; up to `tries` attempts. Returns [expected_rows, written_rows]."""
    last = None
    for attempt in range(1, tries + 1):
        tmp = os.path.join(out, table + ".jsonl.tmp")
        try:
            with psycopg.connect(url, connect_timeout=30, autocommit=True, options="-c default_transaction_read_only=on") as conn:
                cur = conn.cursor()
                cur.execute(f'select count(*) from "{table}"'); expected = cur.fetchone()[0]
                cur.execute(f'select * from "{table}"')
                cols, written = [d.name for d in cur.description], 0
                with open(tmp, "w", encoding="utf-8") as f:
                    for row in cur:
                        f.write(json.dumps(dict(zip(cols, redact_row(table, cols, row))), default=_jsonable) + "\n"); written += 1
            os.replace(tmp, os.path.join(out, table + ".jsonl"))
            return [expected, written]
        except Exception as e:                                 # network drop / pooler timeout: try the whole table again
            last = f"{type(e).__name__}"
            print(f"export retry {attempt}/{tries} for {table}: {last}", flush=True)
            import time
            time.sleep(3 * attempt)
    return f"FAILED ({last})"


def main(root=None):
    import psycopg
    root = root or (sys.argv[1] if len(sys.argv) > 1 else "D:/sindhu_backup_phase0")
    out = os.path.join(root, "cloud_export_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
    os.makedirs(out, exist_ok=False)                      # refuses to reuse a folder
    manifest = {}
    url = _url()
    with psycopg.connect(url, connect_timeout=30, autocommit=True, options="-c default_transaction_read_only=on") as conn:
        tables = [t for (t,) in conn.execute("select tablename from pg_tables where schemaname='public' order by 1").fetchall()]
    for table in tables:
        if table.startswith("auth_"):
            manifest[table] = "SKIPPED (credentials)"; continue
        if "kline" in table or "candle" in table:
            manifest[table] = "SKIPPED (candle table)"; continue
        manifest[table] = _export_table(psycopg, url, table, out)
    json.dump(manifest, open(os.path.join(out, "_manifest.json"), "w"), indent=1)
    bad = [t for t, v in manifest.items() if isinstance(v, str) and v.startswith("FAILED") or (isinstance(v, list) and v[0] != v[1])]
    print("export folder:", out, "| tables:", len(manifest), "| problems:", bad)
    return out


if __name__ == "__main__":
    main()
