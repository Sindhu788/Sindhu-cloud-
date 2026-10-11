"""Explicit reviewed migration entrypoint; production requires owner approval.

Test copies leave the local scanner untouched. Production requires its exclusive
lock, imports every event, then switches local Main/scanner to the same PG wallet
Cloud reads. Imported entries remain PAUSED until an authorized resume.
"""
import argparse
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit,urlunsplit
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--target',choices=['test','production'],required=True)
    parser.add_argument('--approved-project')
    args=parser.parse_args()
    if args.target=='production' and args.approved_project!='snowy-hall-06890228':
        raise ValueError('Explicit owner production approval required')
    root=ROOT/'data/recovery_main/shared_paper'
    lock=None
    if args.target=='production':
        import msvcrt
        lock=open(root/'scanner.lock','r+b');lock.seek(0)
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:
            lock.close();raise ValueError('Stop the identified scanner before production handover') from None
    try:
        import psycopg2
        from trading_intelligence.shared_postgres import PostgresSharedWallet
        from trading_intelligence.shared_transfer import transfer
        settings=json.loads(Path('D:/sindhu/data/config/neon_runtime_connection.json').read_text())
        p=urlsplit(settings['database_url'])
        production_host='ep-tiny-lab-b5cyz6f1.c-7.us-east-2.aws.neon.tech'
        if p.hostname.replace('-pooler.','.')!=production_host or p.path!='/neondb':
            raise ValueError('Configured project/database differs; migration stopped')
        host=production_host if args.target=='production' else 'ep-snowy-paper-b5qdud2p.c-7.us-east-2.aws.neon.tech'
        # Explicit branch host, direct connection for the migration.
        dsn=urlunsplit((p.scheme,p.netloc.rsplit('@',1)[0]+'@'+host,p.path,p.query,p.fragment))
        def connection():return psycopg2.connect(dsn,connect_timeout=10)
        with connection() as raw:
            with raw.cursor() as cursor:cursor.execute((ROOT/'scripts/shared_paper_postgres.sql').read_text())
        receipt=json.loads((root/'owner_session.json').read_text())
        result=transfer(PostgresSharedWallet(connection),root/'wallet.db',receipt['archive_path'],receipt['archive_sha256'])
        if args.target=='production':
            marker=root/'backend.tmp'
            marker.write_text(json.dumps({'backend':'postgres','branch_id':'br-fancy-paper-b5r2ys6l','session_id':result['session_id']}))
            marker.replace(root/'backend.json')
        print(json.dumps({'target':args.target,**result}))
    finally:
        if lock is not None:lock.close()


if __name__=='__main__':
    try:main()
    except Exception as exc:
        # Driver errors may include connection metadata. Never print the DSN.
        print(json.dumps({'status':'STOPPED','error_type':type(exc).__name__,
                          'error':str(exc) if isinstance(exc,ValueError) else 'Migration failed; transaction aborted.'}))
        raise SystemExit(1)
