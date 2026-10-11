from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from trading_intelligence.shared_execution import SharedExecution
from trading_intelligence.shared_wallet import SharedWallet


def setup(tmp_path,monkeypatch):
    monkeypatch.setenv('SINDHU_SAFE_START','0')
    wallet=SharedWallet(tmp_path/'paper.db')
    ident=wallet.create('synthetic-e2e','a'*64,'synthetic')['session_id']
    wallet.event(ident,'resume','control',{'paused':False})
    logs=[]
    engine=SimpleNamespace(_log_decision=lambda *args,**kw:logs.append(args))
    epoch=int(datetime.now(timezone.utc).timestamp()*1000)
    adapter=SharedExecution(wallet,ident,engine,lambda symbol:(100,epoch))
    pick=dict(direction='bullish',entry_price=100,stop_loss=95,take_profit=115,timeframe='1h',strategy_version=1)
    snap={'candle_receipt':{'last_closed_at_ms':epoch//3600000*3600000}}
    return wallet,ident,adapter,pick,snap,logs


def test_post_gate_adapter_shared_cash_queue_and_restart(tmp_path,monkeypatch):
    w,s,a,p,snap,logs=setup(tmp_path,monkeypatch)
    assert a('strategy-a','binance','BTCUSDT',p,snap,{},.1,.5)==(1,0)
    assert a('strategy-b','binance','ETHUSDT',p,snap,{},.1,.5)==(1,0)
    result=SharedWallet(w.path).snapshot(s)
    assert result['open_positions']==2 and result['cash']<80
    assert result['net_pnl']==pytest.approx(result['equity']-100)
    assert result['lifetime']['delivery_success']==0
    with w.connect() as conn:
        assert conn.execute("SELECT count(*) FROM shared_events WHERE kind='notification_queued'").fetchone()[0]==2
    assert a('strategy-a','binance','BTCUSDT',p,snap,{},.1,.5)==(0,0)
    assert w.snapshot(s)['lifetime']['accepted']==2


def test_safe_start_cannot_execute(tmp_path,monkeypatch):
    w,s,a,p,snap,logs=setup(tmp_path,monkeypatch)
    monkeypatch.setenv('SINDHU_SAFE_START','1')
    with pytest.raises(ValueError,match='Safe startup'):
        a('a','binance','BTCUSDT',p,snap,{},.1,.5)
    assert w.snapshot(s)['cash']==100


def test_missing_stale_quotes_and_receipts_fail_closed(tmp_path,monkeypatch):
    w,s,a,p,snap,logs=setup(tmp_path,monkeypatch)
    assert a('a','binance','BTCUSDT',p,{}, {},.1,.5)==(0,1)
    a.quote_provider=lambda symbol:(100,0)
    assert a('a','binance','BTCUSDT',p,snap,{},.1,.5)==(0,1)
    assert w.snapshot(s)['cash']==100


def test_monitor_does_not_award_pre_entry_target(tmp_path,monkeypatch):
    w,s,a,p,snap,logs=setup(tmp_path,monkeypatch)
    a('a','binance','BTCUSDT',p,snap,{},.1,.5)
    position=w.snapshot(s)['positions'][0]
    at=pd.Timestamp(position['entered_at_ms']//900000*900000,unit='ms',tz='UTC')
    frame=pd.DataFrame([dict(open=100,high=120,low=99,close=100)],index=[at])
    receipt=dict(period_ms=900000,last_closed_at_ms=int(at.timestamp()*1000)+900000)
    a.monitor('BTCUSDT',frame,receipt)
    assert w.snapshot(s)['open_positions']==1
    frame.index=frame.index+pd.Timedelta(minutes=15)
    receipt['last_closed_at_ms']+=900000
    a.monitor('BTCUSDT',frame,receipt)
    assert w.snapshot(s)['closed_trades']==1
    assert w.snapshot(s)['wins']==1


def test_monitor_stop_first_and_adverse_gap(tmp_path,monkeypatch):
    w,s,a,p,snap,logs=setup(tmp_path,monkeypatch)
    a('a','binance','BTCUSDT',p,snap,{},.1,.5)
    entry=w.snapshot(s)['positions'][0]['entered_at_ms']
    at=pd.Timestamp(entry//900000*900000+900000,unit='ms',tz='UTC')
    frame=pd.DataFrame([dict(open=90,high=120,low=85,close=100)],index=[at])
    receipt=dict(period_ms=900000,last_closed_at_ms=int(at.timestamp()*1000)+900000)
    a.monitor('BTCUSDT',frame,receipt)
    assert w.snapshot(s)['losses']==1
    with w.connect() as conn:
        state=w._load(conn,s)
        assert float(state['closed'][0]['exit_price'])<90


def test_existing_kill_gate_precedes_shared_execution(test_db,monkeypatch):
    from paper_trading import engine as module
    engine=module.PaperTradingEngine()
    monkeypatch.setattr(module.kill_switch,'is_active',lambda:True)
    engine._shared_execution=lambda *a:pytest.fail('Kill switch must reject before shared execution')
    pick=dict(direction='bullish',entry_price=100,stop_loss=95,take_profit=115,
              strategy_id='synthetic',timeframe='1h',lesson_ids=[])
    assert engine._open_if_allowed('synthetic','binance','BTCUSDT',pick,{}, {'initial_balance':100})==(0,1)


def test_existing_dry_run_gate_precedes_shared_execution(test_db,monkeypatch):
    from paper_trading import engine as module
    engine=module.PaperTradingEngine()
    monkeypatch.setattr(module.risk_manager,'evaluate',lambda *a,**kw:(True,None,.1,.5))
    engine._shared_execution=lambda *a:pytest.fail('Dry run must reject before shared execution')
    pick=dict(direction='bullish',entry_price=100,stop_loss=95,take_profit=115,
              strategy_id='synthetic',timeframe='1h',lesson_ids=[])
    assert engine._open_if_allowed('synthetic','binance','BTCUSDT',pick,{}, {'dry_run':True})==(0,0)
