"""Opt-in real PostgreSQL tests on the existing isolated Neon branch only."""
import concurrent.futures
import json
import os
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit
import uuid
import pytest
from trading_intelligence.shared_postgres import PostgresSharedWallet

TEST_HOST='ep-snowy-paper-b5qdud2p.c-7.us-east-2.aws.neon.tech'
pytestmark=pytest.mark.skipif(os.environ.get('SINDHU_TEST_NEON_HOST')!=TEST_HOST,reason='Explicit isolated branch required')


@pytest.fixture
def pg_wallet():
    import psycopg2
    cfg=json.loads(Path('D:/sindhu/data/config/neon_runtime_connection.json').read_text())
    parts=urlsplit(cfg['database_url'])
    # Reuse the existing authorized cloned role internally; never print DSN.
    auth=parts.netloc.rsplit('@',1)[0]
    dsn=urlunsplit((parts.scheme,auth+'@'+TEST_HOST,parts.path,parts.query,parts.fragment))
    def connect():return psycopg2.connect(dsn,connect_timeout=10)
    with connect() as raw:
        with raw.cursor() as cur:
            cur.execute(Path('scripts/shared_paper_postgres.sql').read_text())
    wallet=PostgresSharedWallet(connect)
    ident=wallet.create('isolated-qa-'+uuid.uuid4().hex,'a'*64,'synthetic')['session_id']
    yield wallet,ident


def test_real_postgres_costs_restart_idempotency(pg_wallet):
    w,s=pg_wallet
    assert w.snapshot(s)['cash']==100
    w.event(s,'resume','control',{'paused':False})
    args=dict(position_id='p',strategy_id='a',symbol='BTCUSDT',price=100,stop=95,target=115,quantity=.1,gates_passed=True)
    first=w.open(s,'open',**args)
    assert w.open(s,'open',**args)==first
    w.close(s,'close','p',115,'target')
    state=PostgresSharedWallet(w.connection_factory).snapshot(s)
    assert state['wins']==1 and state['closed_trades']==1 and state['cash']>100
    with pytest.raises(ValueError,match='Different close'):w.close(s,'close','p',120,'target')


def test_real_postgres_concurrent_symbol_lock(pg_wallet):
    w,s=pg_wallet;w.event(s,'resume','control',{'paused':False})
    def enter(n):
        try:
            w.open(s,str(n),position_id=str(n),strategy_id=str(n),symbol='ETHUSDT',price=100,stop=95,target=115,quantity=.1,gates_passed=True)
            return True
        except ValueError:return False
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(enter,range(4)))
    assert sum(results)==1
    assert w.snapshot(s)['open_positions']==1


def test_real_postgres_foreign_keys_and_rollback(pg_wallet):
    import psycopg2
    w,s=pg_wallet
    with pytest.raises(psycopg2.errors.ForeignKeyViolation):
        with w.connect() as conn:
            w._begin(conn)
            conn.execute('INSERT INTO shared_events(session_id,event_id,at_utc,kind,payload) VALUES (?,?,?,?,?)',('missing','bad','now','scan','{}'))
    assert w.snapshot(s)['cash']==100
    w.event(s,'valid','scan',{'success':True})
    assert w.snapshot(s)['lifetime']['scans_completed']==1


def test_real_postgres_legacy_history_preserved(pg_wallet):
    w,s=pg_wallet
    with w.connect() as conn:
        before=conn.execute("SELECT count(*),md5(string_agg(id::text,',' ORDER BY id)) FROM paper_positions").fetchone()
        archive=conn.execute('SELECT count(*) FROM migration_history.open_paper_positions').fetchone()[0]
    w.event(s,'scan','scan',{'success':True})
    with w.connect() as conn:
        after=conn.execute("SELECT count(*),md5(string_agg(id::text,',' ORDER BY id)) FROM paper_positions").fetchone()
        assert conn.execute('SELECT count(*) FROM migration_history.open_paper_positions').fetchone()[0]==archive
        seq=conn.execute('SELECT sequence FROM shared_events WHERE session_id=? ORDER BY sequence',(s,)).fetchone()[0]
    assert before==after and before[0]==1132 and archive==65 and seq>0


def test_real_postgres_atomic_transfer_no_overwrite(pg_wallet,tmp_path):
    import hashlib
    from trading_intelligence.shared_wallet import SharedWallet
    from trading_intelligence.shared_transfer import transfer
    w,_=pg_wallet
    archive=tmp_path/'archive.db';archive.write_bytes(b'isolated backup fixture')
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    source=tmp_path/'source.db';local=SharedWallet(source)
    ident=local.create('transfer-'+uuid.uuid4().hex,digest,'synthetic')['session_id']
    local.event(ident,'resume','control',{'paused':False})
    local.event(ident,'scan','scan',{'success':True})
    with pytest.raises(ValueError,match='checksum'):transfer(w,source,archive,'0'*64)
    result=transfer(w,source,archive,digest)
    assert result['source_events']==2 and result['imported_events']==3
    assert w.snapshot(ident)['paused'] and w.snapshot(ident)['lifetime']['scans_completed']==1
    with pytest.raises(ValueError,match='no overwrite'):transfer(w,source,archive,digest)
    assert w.snapshot(ident)['lifetime']['scans_completed']==1


def test_real_postgres_api_through_normal_test_login(pg_wallet,tmp_path,monkeypatch):
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from data_engine import config,db_backend
    from sindhu_web import auth,security
    from sindhu_web.api.auth import router as auth_router
    from sindhu_web.api.intelligence import router
    import trading_intelligence.shared_postgres as pg
    w,_=pg_wallet
    # Use a new isolated test account and the actual password/session flow.
    # Owner accounts/sessions and the auth validation function are untouched.
    monkeypatch.setattr(config,'CONFIG_DIR',str(tmp_path))
    monkeypatch.setattr(auth,'db_backend',SimpleNamespace(IS_POSTGRES=False))
    auth.set_credentials('isolated-http-qa','synthetic-login-test-only')
    monkeypatch.setattr(db_backend,'IS_POSTGRES',True)
    monkeypatch.setattr(pg,'configured_wallet',lambda:w)
    app=FastAPI();app.include_router(auth_router);app.include_router(router)
    app.middleware('http')(security.token_guard_middleware)
    client=TestClient(app,base_url='http://127.0.0.1',client=('127.0.0.1',50000))
    assert client.get('/api/intelligence/shared-wallet').status_code==401
    assert client.post('/api/intelligence/shared-wallet/resume').status_code==401
    assert client.post('/api/auth/login',json={'username':'isolated-http-qa','password':'synthetic-login-test-only'}).status_code==200
    response=client.get('/api/intelligence/shared-wallet')
    assert response.status_code==200
    result=response.json()
    assert result['session_id']=='paper-78838b922e874ce9a014ed368e642f64'
    assert result['paused'] and result['scanner']['state']=='NOT_ACTIVATED'
    assert result['network_orders']==0
