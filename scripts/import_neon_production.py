"""Approved, atomic, append-only essential import; refuses nonempty targets."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3

ROOT=Path(__file__).resolve().parents[1]
BACKUP=ROOT/'data/backups/neon_mission1_20261010_essential'


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--approve-production-import',action='store_true',required=True)
    parser.parse_args()
    manifest=json.loads((BACKUP/'backup_manifest.json').read_text())
    for name,digest in manifest['files_sha256'].items():
        assert hashlib.sha256((BACKUP/name).read_bytes()).hexdigest()==digest,'Backup checksum mismatch: '+name
    source=sqlite3.connect((BACKUP/'essential.db').as_uri()+'?mode=ro',uri=True)
    assert source.execute('PRAGMA integrity_check').fetchall()==[('ok',)],'Backup integrity check failed'
    assert not source.execute('PRAGMA foreign_key_check').fetchall(),'Backup foreign key check failed'
    source.close()
    raw=(BACKUP/'migration_payload_sanitized.json').read_bytes()
    fingerprint=hashlib.sha256(raw).hexdigest();payload=json.loads(raw)
    assert payload['project_id']=='snowy-hall-06890228','Incorrect Neon project'
    assert sum(payload['counts'].values())==8126,'Unexpected essential record count'
    assert not re.search(rb'(?:bot)?\d{5,15}(?::|%3[aA])[A-Za-z0-9_-]{20,}',raw),'Plaintext credential pattern detected'
    verification=json.loads((BACKUP/'compact_verification.json').read_text())
    credential=json.loads((ROOT/'data/config/neon_runtime_connection.json').read_text())
    from urllib.parse import urlsplit,unquote
    import ssl
    from pg8000 import dbapi
    url=urlsplit(credential['database_url'])
    conn=dbapi.connect(user=unquote(url.username),password=unquote(url.password),host=url.hostname,
                      port=url.port or 5432,database=url.path.lstrip('/'),
                      ssl_context=ssl.create_default_context(),timeout=120)
    try:
        try:
            with closing(conn.cursor()) as cur:
                cur.execute("SET LOCAL statement_timeout='120s'")
                cur.execute("SELECT pg_advisory_xact_lock(hashtext('sindhu-essential-migration-20261010'))")
                cur.execute("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%' AND c.relkind IN ('r','p','v','m','S','f')")
                assert cur.fetchone()[0]==0,'Production is not empty; import refused without changing data'
                for sql in payload['schema']+payload['inserts']+payload['sequences']:cur.execute(sql)
                cur.execute(verification['hash_sql']);results=cur.fetchall()
                mismatches=[name for name,count,ok in results if not ok]
                assert len(results)==43 and not mismatches,'Value/hash verification failed: '+','.join(mismatches)
                for sql in verification['sequence_checks']:
                    cur.execute(sql)
                    assert cur.fetchone()[0]==0,'Sequence verification failed'
                cur.execute("SELECT count(*) FROM telegram_message_log t LEFT JOIN migration_history.all_paper_positions p ON p.id=t.position_id WHERE t.position_id IS NOT NULL AND p.id IS NULL")
                missing=cur.fetchone()[0]
                assert missing==12,'Historical Telegram reference count differs: '+str(missing)
                cur.execute("SELECT count(*) FROM paper_positions WHERE status='open'")
                assert cur.fetchone()[0]==0,'Historical open positions reached the active session'
                cur.execute("CREATE TABLE migration_history.import_receipts (migration_id TEXT PRIMARY KEY,payload_sha256 TEXT NOT NULL,essential_records BIGINT NOT NULL,verified_at TIMESTAMPTZ NOT NULL DEFAULT now())")
                cur.execute("INSERT INTO migration_history.import_receipts(migration_id,payload_sha256,essential_records) VALUES (%s,%s,%s)",('essential-20261010',fingerprint,8126))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        print(json.dumps({'production_import':'PASS','essential_tables':43,'essential_records':8126,'value_hashes_verified':43,'sequences_verified':19,'preserved_missing_telegram_references':missing,'active_historical_open_positions':0}))
    finally:conn.close()


if __name__=='__main__':
    try:main()
    except Exception as exc:
        message=re.sub(r'postgres(?:ql)?://\S+','[REDACTED_DATABASE_URL]',str(exc))
        message=re.sub(r'(?:bot)?\d{5,15}:[A-Za-z0-9_-]{20,}','[REDACTED_TOKEN]',message)
        print(json.dumps({'production_import':'FAIL','transaction_committed':False,'error_type':type(exc).__name__,'error':message}))
        raise SystemExit(1)
