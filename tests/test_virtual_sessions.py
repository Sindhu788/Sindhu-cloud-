import sqlite3
import pytest
from trading_intelligence import sessions


def test_persistent_example_is_isolated_and_idempotent(monkeypatch):
    from data_engine import db_backend
    monkeypatch.setattr(db_backend,'IS_POSTGRES',False)
    conn=sqlite3.connect(':memory:')
    conn.execute('PRAGMA foreign_keys=ON')
    first=sessions.create_session(conn);second=sessions.create_session(conn);conn.commit()
    assert first['initial_balance']==100 and first['open_positions']==0
    result=sessions.run_example(conn,first['session_id']);conn.commit()
    retry=sessions.run_example(conn,first['session_id']);conn.commit()
    assert result==retry and result['network_orders']==0 and result['open_positions']==0
    assert len(result['closed_trades'])==1 and result['cash']!=100
    assert conn.execute('SELECT count(*) FROM intelligence_virtual_events').fetchone()[0]==2
    assert sessions.load_session(conn,second['session_id']).snapshot()['cash']==100
    assert not conn.execute('PRAGMA foreign_key_check').fetchall()
    with pytest.raises(ValueError,match='not found'):
        sessions.load_session(conn,'missing')


def test_global_telegram_dryrun_prevents_network(monkeypatch):
    from paper_trading import telegram_bot
    monkeypatch.setenv('SINDHU_TELEGRAM_DRY_RUN','1')
    monkeypatch.setattr(telegram_bot.requests,'post',lambda *a,**k:pytest.fail('Unexpected network'))
    monkeypatch.setattr(telegram_bot,'load_settings',lambda:pytest.fail('Unexpected credential access'))
    ok,error=telegram_bot._raw_send('Private synthetic exercise')
    assert not ok and 'dry-run' in error
