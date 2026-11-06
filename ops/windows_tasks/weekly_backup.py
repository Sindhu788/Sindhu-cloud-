"""Master plan A24 (P41 + P42 + P23): weekly Cloud database backup, restore test and storage check.
1. Export every Cloud table READ-ONLY (scripts/backup_cloud_export.py, secrets redacted), zip it into D:\\sindhu_backups\\pg\\YYYY-WW\\ and
   write its SHA-256. Older backups are NOT deleted automatically (owner rule: never delete backups); the log shows how many exist.
2. Restore test into a THROWAWAY SQLite file (scripts/restore_export_to_sqlite.py): exit 0 only if every row count matches.
3. Storage check: database size vs the 0.5 GB free limit (warning at 70 %), the 5 biggest tables, and a DRY RUN of retention cleanup
   (rows older than 90 days in log/telemetry tables only; trades and the wallet journal are never candidates). Nothing is deleted.
One line per run is appended to D:\\sindhu_backups\\BACKUP_LOG.md. Usage (stable venv): python ops/windows_tasks/weekly_backup.py [--check-only]"""
import argparse
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = os.environ.get("SINDHU_BACKUP_DIR", r"D:\sindhu_backups")
CONN_FILE = os.environ.get("SINDHU_NEON_FILE", r"D:\sindhu\data\config\neon_runtime_connection.json")
LOG_TABLES = {"paper_scan_log": "completed_at", "paper_decision_log": "created_at", "activity_log": "created_at", "audit_trail_log": "created_at"}


def storage_check():
    import psycopg
    url = os.environ.get("DATABASE_URL") or json.load(open(CONN_FILE, encoding="utf-8"))["database_url"]
    out = {}
    with psycopg.connect(url, connect_timeout=15) as c:
        c.read_only = True
        size = c.execute("SELECT pg_database_size(current_database())").fetchone()[0]
        out["size_mb"] = round(size / 1e6, 1)
        out["pct_of_free_limit"] = round(size / 512e6 * 100, 1)
        out["top_tables_mb"] = [(r[0], round(r[1] / 1e6, 1)) for r in c.execute(
            "SELECT relname, pg_total_relation_size(relid) FROM pg_catalog.pg_statio_user_tables ORDER BY 2 DESC LIMIT 5").fetchall()]
        cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        dry = {}
        for table, col in LOG_TABLES.items():
            try:
                dry[table] = c.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} < %s", (cutoff,)).fetchone()[0]
            except Exception as e:
                dry[table] = f"n/a ({type(e).__name__})"
                c.rollback()
        out["retention_dry_run_rows_older_than_90d"] = dry
    out["warning"] = out["pct_of_free_limit"] >= 70
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-only", action="store_true", help="storage check only (no export)")
    a = ap.parse_args()
    st = storage_check()
    print("storage:", json.dumps(st))
    if a.check_only:
        return
    now = datetime.now(timezone.utc)
    week = f"{now:%G}-W{now:%V}"
    dest = os.path.join(BASE, "pg", week)
    os.makedirs(dest, exist_ok=True)
    py = sys.executable
    r = subprocess.run([py, os.path.join(ROOT, "scripts", "backup_cloud_export.py")], capture_output=True, text=True, timeout=3600)
    line = [x for x in r.stdout.splitlines() if x.startswith("export folder:")]
    if not line:
        print("export failed:", r.stdout[-300:], r.stderr[-300:])
        sys.exit(1)
    folder = line[-1].split("export folder:")[1].split("|")[0].strip()
    stem = os.path.join(dest, f"cloud_export_{now:%Y%m%d_%H%M%S}")
    zpath = shutil.make_archive(stem, "zip", folder)
    sha = hashlib.sha256(open(zpath, "rb").read()).hexdigest()
    open(zpath + ".sha256", "w").write(sha)
    scratch = os.path.join(dest, f"restore_test_{now:%H%M%S}.sqlite")
    rt = subprocess.run([py, os.path.join(ROOT, "scripts", "restore_export_to_sqlite.py"), folder, scratch], capture_output=True, text=True, timeout=3600)
    n_backups = len(glob.glob(os.path.join(BASE, "pg", "*", "*.zip")))
    entry = (f"| {now:%Y-%m-%d %H:%M} | {week} | {os.path.basename(zpath)} sha256 {sha[:16]} | restore exit {rt.returncode} | "
             f"{st['size_mb']} MB ({st['pct_of_free_limit']} % of 0.5 GB){' WARNING' if st['warning'] else ''} | {n_backups} |")
    log = os.path.join(BASE, "BACKUP_LOG.md")
    if not os.path.exists(log):
        open(log, "w", encoding="utf-8").write("| UTC | Week | Archive | Restore test | Database size | Backups on disk |\n|---|---|---|---|---|---|\n")
    open(log, "a", encoding="utf-8").write(entry + "\n")
    print(entry)


if __name__ == "__main__":
    main()
