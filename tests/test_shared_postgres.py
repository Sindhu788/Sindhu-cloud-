"""Driver transaction/parameter contract, without owner credentials or data."""
import pytest
from trading_intelligence.shared_postgres import PostgresSharedWallet, LOCK_KEY


class Raw:
    def __init__(self):self.calls=[];self.closed=False;self.failed=False
    def __enter__(self):return self
    def __exit__(self,typ,*args):self.failed=typ is not None
    def cursor(self):return self
    def execute(self,sql,params):self.calls.append((sql,params))
    def fetchone(self):return ('a','b')
    def __iter__(self):return iter([(1,'row')])
    def close(self):self.closed=True


def test_postgres_write_lock_and_parameter_binding():
    raw=Raw();wallet=PostgresSharedWallet(lambda:raw)
    with wallet.connect() as conn:
        wallet._begin(conn)
        result=conn.execute('SELECT payload WHERE event_id=?',('untrusted\'value',))
        assert result.fetchone()==('a','b')
        assert list(result)==[(1,'row')]
    assert raw.calls[1]==('SELECT pg_advisory_xact_lock(%s)',(LOCK_KEY,))
    assert raw.calls[2]==('SELECT payload WHERE event_id=%s',('untrusted\'value',))
    assert raw.closed and not raw.failed


def test_postgres_failure_rolls_back_and_closes():
    raw=Raw();wallet=PostgresSharedWallet(lambda:raw)
    with pytest.raises(ValueError):
        with wallet.connect():raise ValueError('synthetic failure')
    assert raw.failed and raw.closed


def test_local_backend_requires_explicit_valid_marker(tmp_path):
    import json
    from trading_intelligence.shared_wallet import SharedWallet
    from trading_intelligence.shared_postgres import local_wallet
    original=SharedWallet(tmp_path/'wallet.db')
    assert local_wallet(tmp_path).path==original.path
    (tmp_path/'backend.json').write_text(json.dumps({'backend':'postgres','branch_id':'wrong-branch'}))
    with pytest.raises(ValueError,match='Unapproved'):local_wallet(tmp_path)


def test_production_migration_requires_explicit_approval(monkeypatch):
    import runpy,sys
    script=runpy.run_path('scripts/stage_shared_postgres.py',run_name='isolated_test')
    monkeypatch.setattr(sys,'argv',['stage_shared_postgres.py','--target','production'])
    with pytest.raises(ValueError,match='approval'):script['main']()
