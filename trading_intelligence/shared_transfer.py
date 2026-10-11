"""Explicit, atomic SQLite-to-PostgreSQL journal transfer; no upserts/deletes."""
import hashlib
from pathlib import Path
import sqlite3
import uuid
from trading_intelligence.shared_wallet import SharedWallet


def transfer(wallet, source, archive, expected_sha256):
    if hashlib.sha256(Path(archive).read_bytes()).hexdigest()!=expected_sha256:
        raise ValueError('Archive checksum differs; import stopped')
    snapshot=sqlite3.connect(':memory:')
    original=sqlite3.connect(Path(source).resolve().as_uri()+'?mode=ro',uri=True)
    try:original.backup(snapshot)
    finally:original.close()
    try:
        if snapshot.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or snapshot.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('Source restore integrity failed; import stopped')
        sessions=snapshot.execute('SELECT session_id,name,created_at,data_label,archive_sha256 FROM shared_sessions').fetchall()
        if len(sessions)!=1 or sessions[0][4]!=expected_sha256:
            raise ValueError('Exactly one archive-matched source session required')
        ident=sessions[0][0]
        events=snapshot.execute('SELECT session_id,event_id,at_utc,kind,payload FROM shared_events ORDER BY sequence').fetchall()
        source_wallet=SharedWallet(source,initialize=False)
        before=source_wallet._snapshot(source_wallet._load(snapshot,ident))
        with wallet.connect() as conn:
            wallet._begin(conn)
            # Any existing session with this identity/name blocks import. All
            # other live sessions also block a second owner wallet.
            if conn.execute("SELECT 1 FROM shared_sessions WHERE session_id=? OR name=? OR (data_label='live' AND ?='live')",(ident,sessions[0][1],sessions[0][3])).fetchone():
                raise ValueError('Destination contains a conflicting wallet; no overwrite allowed')
            conn.execute('INSERT INTO shared_sessions VALUES (?,?,?,?,?)',sessions[0])
            for event in events:
                conn.execute('INSERT INTO shared_events(session_id,event_id,at_utc,kind,payload) VALUES (?,?,?,?,?)',event)
            copied=list(conn.execute('SELECT session_id,event_id,at_utc,kind,payload FROM shared_events WHERE session_id=? ORDER BY sequence',(ident,)))
            if copied!=events or wallet._snapshot(wallet._load(conn,ident))!=before:
                raise ValueError('Imported journal integrity differs; transaction rolled back')
            # Preserve every original event, then fail closed for handover.
            wallet._append(conn,ident,'migration-pause-'+uuid.uuid4().hex,'control',{'paused':True})
        return {'session_id':ident,'source_events':len(events),'imported_events':len(events)+1,
                'integrity':'PASS','paused':True,'real_orders':0}
    finally:snapshot.close()
