"""Append-only active-session selection; previous live sessions stay intact."""
import uuid
from trading_intelligence.shared_wallet import now


def active_session(wallet, *, postgres):
    with wallet.connect() as conn:
        sql=("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name='shared_session_selections'"
             if postgres else "SELECT name FROM sqlite_master WHERE type='table' AND name='shared_session_selections'")
        exists=conn.execute(sql).fetchone()
        if exists:
            selected=conn.execute("SELECT session_id FROM shared_session_selections ORDER BY sequence DESC LIMIT 1").fetchone()
            if selected:
                row=conn.execute("SELECT session_id FROM shared_sessions WHERE session_id=? AND data_label='live'",(selected[0],)).fetchone()
                if not row:raise ValueError("Active shared session is invalid")
                return row[0]
        rows=list(conn.execute("SELECT session_id FROM shared_sessions WHERE data_label='live'"))
    if len(rows)!=1:raise ValueError("Exactly one selected shared wallet required")
    return rows[0][0]


def fresh_selection(wallet, *, expected_previous, name, archive_sha256, postgres):
    """Caller needs explicit approval and must migrate the additive table first."""
    if active_session(wallet,postgres=postgres)!=expected_previous:
        raise ValueError("Previous active session differs; handover stopped")
    with wallet.connect() as conn:
        wallet._begin(conn)
        previous=wallet._load(conn,expected_previous)
        if not previous['paused'] or previous['positions']:
            raise ValueError("Pause previous entries and reconcile open positions before handover")
        if previous['archive_sha256']!=archive_sha256:
            raise ValueError("Verified historical backup hash differs")
        if conn.execute("SELECT 1 FROM shared_sessions WHERE name=?",(name,)).fetchone():
            raise ValueError("Session name already exists; no overwrite allowed")
        latest=conn.execute("SELECT session_id FROM shared_session_selections ORDER BY sequence DESC LIMIT 1").fetchone()
        if latest and latest[0]!=expected_previous:
            raise ValueError("Concurrent session handover detected")
        ident='paper-'+uuid.uuid4().hex
        conn.execute("INSERT INTO shared_sessions VALUES (?,?,?,?,?)",(ident,name,now(),'live',archive_sha256))
        conn.execute("INSERT INTO shared_session_selections(session_id,selected_at_utc) VALUES (?,?)",(ident,now()))
    return wallet.snapshot(ident)
