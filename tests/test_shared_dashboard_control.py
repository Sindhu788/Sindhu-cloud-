from unittest.mock import Mock
import pytest
from trading_intelligence import shared_control,cloud_shared_scanner
from trading_intelligence.shared_wallet import SharedWallet


def wallet(tmp_path,monkeypatch):
    from sindhu_web.api import intelligence
    from paper_trading import kill_switch
    from data_engine import feature_toggles
    w=SharedWallet(tmp_path/'wallet.db');ident=w.create('preserved','a'*64)['session_id']
    monkeypatch.setattr(intelligence,'_postgres_shared_wallet',lambda:(w,ident))
    monkeypatch.setattr(kill_switch,'is_active',lambda:False)
    monkeypatch.setattr(feature_toggles,'is_master_paused',lambda:False)
    return w,ident


def test_combined_balance_is_one_wallet_not_independent_books(tmp_path):
    w=SharedWallet(tmp_path/'wallet.db');s=w.create('fresh','a'*64)
    r=shared_control.account_status(s,{'running':True,'state':'RUNNING'})
    assert r['balance']==r['cash']==r['initial_balance']==100
    assert r['closed_trades']==r['open_trades']==0
    assert r['win_rate_pct'] is None and r['account_mode']=='shared_wallet'
    assert r['running'] is False # entries begin paused


def test_start_stop_preserve_journal_and_monitoring(tmp_path,monkeypatch):
    w,ident=wallet(tmp_path,monkeypatch)
    launch=Mock();stop=Mock()
    monkeypatch.setattr(cloud_shared_scanner,'start',launch)
    monkeypatch.setattr(cloud_shared_scanner,'stop',stop)
    shared_control.control('start');assert w.snapshot(ident)['paused'] is False
    shared_control.control('stop');s=w.snapshot(ident)
    assert s['paused'] is True and s['cash']==100
    launch.assert_called_once();stop.assert_not_called()
    with w.connect() as c:
        assert c.execute('select count(*) from shared_events').fetchone()[0]==2


def test_kill_switch_blocks_start_without_resuming_wallet(tmp_path,monkeypatch):
    from paper_trading import kill_switch
    w,ident=wallet(tmp_path,monkeypatch)
    monkeypatch.setattr(kill_switch,'is_active',lambda:True)
    with pytest.raises(ValueError,match='Kill switch'):shared_control.control('start')
    assert w.snapshot(ident)['paused'] is True


def test_existing_api_start_cannot_start_legacy_engine(monkeypatch):
    from sindhu_web.api import paper_trading as api
    monkeypatch.setenv('SINDHU_SHARED_PAPER_ENABLED','1')
    control=Mock(return_value={'ok':True});legacy=Mock()
    monkeypatch.setattr(shared_control,'control',control)
    monkeypatch.setattr(api.engine,'start',legacy)
    assert api.start_engine()=={'ok':True}
    control.assert_called_once_with('start');legacy.assert_not_called()


def test_shared_status_failure_never_falls_back_to_5712(monkeypatch):
    from fastapi import HTTPException
    from sindhu_web.api import paper_trading as api
    monkeypatch.setenv('SINDHU_SHARED_PAPER_ENABLED','1')
    monkeypatch.setattr(shared_control,'status',Mock(side_effect=ValueError('unavailable')))
    legacy=Mock(return_value={'balance':5712});monkeypatch.setattr(api.engine,'status',legacy)
    with pytest.raises(HTTPException) as e:api.get_status()
    assert e.value.status_code==503;legacy.assert_not_called()


def test_settings_cannot_reset_shared_starting_cash(monkeypatch):
    from fastapi import HTTPException
    from sindhu_web.api import paper_trading as api
    monkeypatch.setenv('SINDHU_SHARED_PAPER_ENABLED','1')
    with pytest.raises(HTTPException) as e:api.update_settings(api.SettingsUpdate(initial_balance=5712))
    assert e.value.status_code==422


@pytest.mark.parametrize('method,path',[('get','/api/paper-trading/status'),('post','/api/paper-trading/start'),('post','/api/paper-trading/stop')])
def test_combined_controls_require_normal_auth(method,path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sindhu_web.api.paper_trading import router
    from sindhu_web.security import token_guard_middleware
    app=FastAPI();app.include_router(router);app.middleware('http')(token_guard_middleware)
    response=getattr(TestClient(app,base_url='http://127.0.0.1',client=('127.0.0.1',50000)),method)(path)
    assert response.status_code==401
