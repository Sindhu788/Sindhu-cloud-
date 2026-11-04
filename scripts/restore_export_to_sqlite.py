"""Test-restore a Cloud export into a THROWAWAY SQLite file and verify row counts per table against the manifest.

  python scripts/restore_export_to_sqlite.py <export_folder> <new_sqlite_file>

Never touches production: the target must not exist. Tables that exist in the SINDHU SQLite schema are loaded into it
(columns the local schema does not have are reported as 'dropped columns'); tables that only exist in the Cloud are created
generically (all columns untyped). Exit code 0 only if every table's restored count equals the exported count.
"""
import json
import os
import sqlite3
import sys


def restore(export_dir, target):
    if os.path.exists(target):
        raise SystemExit(f"refusing to overwrite existing file: {target}")
    manifest = json.load(open(os.path.join(export_dir, "_manifest.json"), encoding="utf-8"))
    os.environ.setdefault("SINDHU_DATA_DIR", os.path.dirname(os.path.abspath(target)))
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, here)
    from data_engine import storage
    storage.DB_PATH = target
    storage.init_db()
    conn = sqlite3.connect(target)
    report = []
    for table, info in manifest.items():
        if not isinstance(info, list):
            report.append((table, "skipped", info, None, "")); continue
        rows = [json.loads(line) for line in open(os.path.join(export_dir, table + ".jsonl"), encoding="utf-8")]
        have = [r[1] for r in conn.execute(f'pragma table_info("{table}")')]
        cols = list(rows[0].keys()) if rows else have
        note = ""
        if not have and not rows:
            report.append((table, "ok" if info[0] == 0 else "MISMATCH", info[0], 0, "empty table, no local schema")); continue
        if not have:
            conn.execute(f'create table "{table}" (' + ", ".join(f'"{c}"' for c in cols) + ")")
            have = cols; note = "created generically"
        use = [c for c in cols if c in have]
        dropped = [c for c in cols if c not in have]
        if dropped:
            note = (note + " ").strip() + f" dropped columns: {dropped}"
        conn.execute(f'delete from "{table}"')
        conn.executemany(f'insert or replace into "{table}" ({",".join(chr(34) + c + chr(34) for c in use)}) values ({",".join("?" * len(use))})',
                         [tuple(json.dumps(r[c]) if isinstance(r[c], (dict, list)) else r[c] for c in use) for r in rows])
        restored = conn.execute(f'select count(*) from "{table}"').fetchone()[0]
        report.append((table, "ok" if restored == info[0] else "MISMATCH", info[0], restored, note))
    conn.commit(); conn.close()
    return report


if __name__ == "__main__":
    rep = restore(sys.argv[1], sys.argv[2])
    ok = all(r[1] in ("ok", "skipped") for r in rep)
    for r in rep:
        if r[1] != "skipped" and (r[1] != "ok" or r[4]):
            print(r)
    print(f"tables restored: {sum(r[1] == 'ok' for r in rep)} ok, {sum(r[1] == 'MISMATCH' for r in rep)} mismatched, {sum(r[1] == 'skipped' for r in rep)} skipped; "
          f"rows restored: {sum(r[3] or 0 for r in rep)}")
    sys.exit(0 if ok else 1)
