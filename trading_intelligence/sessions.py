"""Append-only virtual session events, separate from historical paper trades."""
from datetime import datetime,timezone
import json
import uuid

from trading_intelligence.virtual import VirtualLedger


def bootstrap(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS intelligence_virtual_sessions(session_id TEXT PRIMARY KEY,initial_balance DOUBLE PRECISION NOT NULL,data_label TEXT NOT NULL,created_at TEXT NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS intelligence_virtual_events(session_id TEXT NOT NULL REFERENCES intelligence_virtual_sessions(session_id),event_id TEXT NOT NULL,operation TEXT NOT NULL,event_json TEXT NOT NULL,PRIMARY KEY(session_id,event_id))')


def create_session(conn):
    bootstrap(conn)
    ident='virtual-'+uuid.uuid4().hex
    conn.execute('INSERT INTO intelligence_virtual_sessions(session_id,initial_balance,data_label,created_at) VALUES (?,?,?,?)',(ident,100,'synthetic',datetime.now(timezone.utc).isoformat()))
    return VirtualLedger(ident,100,data_label='synthetic').snapshot()


def load_session(conn,ident):
    row=conn.execute('SELECT initial_balance,data_label FROM intelligence_virtual_sessions WHERE session_id=?',(ident,)).fetchone()
    if not row:raise ValueError('Virtual session not found')
    ledger=VirtualLedger(ident,float(row[0]),data_label=row[1])
    events=conn.execute('SELECT operation,event_json FROM intelligence_virtual_events WHERE session_id=? ORDER BY event_id',(ident,)).fetchall()
    for operation,raw in events:
        event=json.loads(raw)
        if operation=='open':ledger.open(**event)
        elif operation=='close':ledger.close(**event)
        else:raise ValueError('Unknown stored virtual event')
    return ledger


def run_example(conn,ident):
    """One deterministic fixture round trip; retry returns its existing result.

    Prices are from the versioned synthetic fixture, with an explicit 5 bps
    adverse slippage and 10 bps fees per side. No exchange prices are invented.
    """
    from pathlib import Path
    from data_engine import db_backend
    if db_backend.IS_POSTGRES:
        conn.execute('SELECT session_id FROM intelligence_virtual_sessions WHERE session_id=? FOR UPDATE',(ident,)).fetchone()
    else:conn.execute('BEGIN IMMEDIATE')
    ledger=load_session(conn,ident)
    fixture=json.loads((Path(__file__).with_name('fixtures')/'exam_inputs.json').read_text())[0]
    candles=fixture['candles']
    entry=float(candles[0]['open'])*1.0005;exit_price=float(candles[-1]['close'])*.9995
    prior=conn.execute('SELECT count(*) FROM intelligence_virtual_events WHERE session_id=?',(ident,)).fetchone()[0]
    if not prior:
        opening={'position_id':'synthetic-example','price':entry,'quantity':10/entry,
                 'reason':'Explicit synthetic accounting exercise: '+fixture['id'],'fee_bps':10}
        closing={'position_id':'synthetic-example','price':exit_price,'fee_bps':10}
        ledger.open(**opening);ledger.close(**closing)
        for event_id,operation,event in [('example-001','open',opening),('example-002','close',closing)]:
            conn.execute('INSERT INTO intelligence_virtual_events(session_id,event_id,operation,event_json) VALUES (?,?,?,?)',(ident,event_id,operation,json.dumps(event)))
    return {**ledger.snapshot(),'example_fixture':fixture['id'],'closed_trades':ledger.closed,
            'fee_bps':10,'slippage_bps':5,'telegram_mode':'dry-run','network_orders':0,
            'signal_decision':'NO_TRADE','reason':'Accounting exercise only; fixture has insufficient trading evidence.'}
