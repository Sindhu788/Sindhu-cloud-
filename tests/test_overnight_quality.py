"""Operational regression tests use isolated fixtures and never production auth."""
from datetime import datetime, timedelta, timezone
import json
import sqlite3
import pytest


def test_safe_start_blocks_every_scanner_entry_before_network_or_writes(monkeypatch):
    from paper_trading.engine import PaperTradingEngine
    from paper_trading import engine as module
    e=PaperTradingEngine()
    monkeypatch.setenv('SINDHU_SAFE_START','1')
    monkeypatch.setattr(module.kill_switch,'is_active',lambda:pytest.fail('Safe-start gate must run first'))
    for operation in (e.start,e.run_single_tick_now,lambda:e.run_single_coin_scan_now('BTCUSDT')):
        with pytest.raises(RuntimeError,match='Safe startup'):
            operation()
    assert not e.is_running() and e._current_scan is None


def test_scan_receipts_survive_new_process_and_block_overlap(test_db,monkeypatch):
    from paper_trading.engine import PaperTradingEngine
    from paper_trading import engine as module
    monkeypatch.delenv('SINDHU_SAFE_START',raising=False)
    monkeypatch.setattr(module.kill_switch,'is_active',lambda:False)
    e=PaperTradingEngine()
    def fake_pipeline():
        e._current_scan.update(coins_scanned=3,candidates=2)
        e._log_decision('synthetic','QA',{},'rejected','Synthetic risk limit',{})
        e._log_decision('synthetic','QA',{},'dry_run','Synthetic approved candidate',{})
        with pytest.raises(RuntimeError,match='already in progress'):
            e.run_single_tick_now()
    monkeypatch.setattr(e,'_tick_impl',fake_pipeline)
    e.run_single_tick_now()
    with sqlite3.connect(test_db) as conn:
        assert conn.execute('SELECT coins_scanned,candidates,rejected,accepted,outcome FROM paper_scan_log').fetchone()==(3,2,1,1,'complete')
    assert PaperTradingEngine()._last_tick_at is None
    with sqlite3.connect(test_db) as conn:
        assert conn.execute('SELECT count(*) FROM paper_scan_log').fetchone()[0]==1


def test_scan_error_records_partial_failure_and_clears_progress(test_db,monkeypatch):
    from paper_trading.engine import PaperTradingEngine
    from paper_trading import engine as module
    monkeypatch.delenv('SINDHU_SAFE_START',raising=False)
    monkeypatch.setattr(module.kill_switch,'is_active',lambda:False)
    e=PaperTradingEngine()
    def fail():
        e._scan_progress['in_progress']=True
        raise ValueError('synthetic error')
    monkeypatch.setattr(e,'_tick_impl',fail)
    with pytest.raises(ValueError):e.run_single_tick_now()
    assert not e._scan_progress['in_progress']
    assert e._scan_lock.acquire(blocking=False)
    e._scan_lock.release()
    with sqlite3.connect(test_db) as conn:
        assert conn.execute('SELECT outcome,errors,reason FROM paper_scan_log').fetchone()==('error',1,'ValueError')


def test_no_candidate_is_explicit_no_trade_without_opening_position(monkeypatch):
    from paper_trading.engine import PaperTradingEngine
    from paper_trading import engine as m
    monkeypatch.setattr(m.strategy_matcher,'relevant_strategies',lambda *a:[])
    monkeypatch.setattr(m.lesson_matcher,'relevant_lessons',lambda *a:[])
    monkeypatch.setattr(m.signal_generator,'generate_candidates',lambda *a:[])
    e=PaperTradingEngine()
    assert e._process_coin('synthetic','QA',{'market_state':'ranging'}, {})==(0,0)
    assert e._pending_decisions[0]['decision']=='no_trade'
    assert 'No eligible strategies' in e._pending_decisions[0]['reason']


def test_diagnostics_read_only_and_missing_counters_are_unknown(test_db,monkeypatch,tmp_path):
    from sindhu_web.api import quality
    from data_engine import paths
    monkeypatch.setattr(paths,'CONFIG_DIR',str(tmp_path))
    (tmp_path/'paper_trading_settings.json').write_text(json.dumps({'engine_enabled':False,'dry_run':True}))
    (tmp_path/'telegram_settings.json').write_text(json.dumps({'bot_token':'sentinel-private-token','personal_chat_id':'sentinel-private-id'}))
    with sqlite3.connect(test_db) as conn:
        before=conn.total_changes
        data=quality.build_diagnostics(conn)
        assert conn.total_changes==before
        assert 'paper_scan_log' not in quality.tables(conn)
    assert data['counts']['scans'] is None and data['counts']['candidates'] is None
    assert data['counts']['saved_decisions']==0
    assert data['telegram']['token_present']
    assert 'sentinel-private' not in json.dumps(data)
    assert data['market_data']['freshness'] is None


def test_diagnostics_rolling_window_and_notification_types(test_db,monkeypatch,tmp_path):
    from sindhu_web.api import quality
    from paper_trading.scan_telemetry import write_receipt
    from data_engine import paths
    monkeypatch.setattr(paths,'CONFIG_DIR',str(tmp_path))
    now=datetime.now(timezone.utc)
    with sqlite3.connect(test_db) as conn:
        for when in (now-timedelta(hours=25),now-timedelta(hours=1)):
            write_receipt(conn,dict(started_at=when.isoformat(),completed_at=when.isoformat(),kind='fixture',outcome='complete',reason='',coins_scanned=4,candidates=3,rejected=2,accepted=1,no_trade=0,errors=0))
        data=quality.build_diagnostics(conn,now)
    assert data['counts']['scans']==1 and data['counts']['coins_scanned']==4
    assert data['counts']['candidates']==3
    assert 'No pre-upgrade' in data['telemetry_coverage']


def test_public_preview_contains_no_private_data_and_admin_requires_auth(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sindhu_web import security
    from sindhu_web.api.quality import router
    app=FastAPI();app.include_router(router);app.middleware('http')(security.token_guard_middleware)
    monkeypatch.setattr(security.auth,'is_valid_session',lambda t:False)
    c=TestClient(app,base_url='http://127.0.0.1',client=('127.0.0.1',1234))
    response=c.get('/preview')
    assert response.status_code==200
    assert response.headers['cache-control']=='no-store'
    assert '/static/js/control_room.js?v=' in response.text
    assert '/static/css/control_room.css?v=' in response.text
    assert c.get('/api/quality/preview').json()['private_data_available'] is False
    for path in ('/api/quality/diagnostics','/api/quality/journal','/api/paper-trading/catalog/strategies'):
        assert c.get(path).status_code==401
    assert c.post('/api/quality/preview',json={}).status_code==401
    assert c.get('/control-room',follow_redirects=False).status_code==307


def test_main_cloud_catalogs_and_controls_have_real_http_contract(test_db,monkeypatch,tmp_path):
    from fastapi.testclient import TestClient
    import sindhu_web.server as main
    import cloud_runtime.app as cloud
    from sindhu_web import security
    from data_engine import paths
    monkeypatch.setattr(paths,'CONFIG_DIR',str(tmp_path))
    monkeypatch.setattr(security.auth,'is_valid_session',lambda t:t=='qa-only')
    monkeypatch.setattr(security,'get_or_create_token',lambda:'qa-only-csrf')
    for app in (main.app,cloud.app):
        c=TestClient(app,base_url='http://127.0.0.1',client=('127.0.0.1',1234))
        c.cookies.set(security.auth.SESSION_COOKIE,'qa-only')
        assert c.get('/control-room').status_code==200
        assert c.get('/api/quality/diagnostics').status_code==200
        assert len(c.get('/api/paper-trading/catalog/strategies').json()['strategies'])==154
        assert c.get('/api/paper-trading/catalog/lessons').json()['lessons']==[]
        assert c.post('/api/paper-trading/start',json={}).status_code==401
        c.headers['X-Sindhu-Token']='qa-only-csrf'
        for path in ('/api/paper-trading/start','/api/paper-trading/run-tick-now','/api/paper-trading/run-coin-scan-now/BTCUSDT'):
            r=c.post(path,json={});assert r.status_code==409 and 'Safe startup' in r.json()['detail']


def test_settings_reload_history_and_virtual_retry_are_isolated(test_db,monkeypatch,tmp_path):
    from data_engine import config as base
    from paper_trading import config
    from sindhu_web.api import paper_trading as api
    from trading_intelligence.sessions import create_session,run_example,load_session
    monkeypatch.setattr(base,'CONFIG_DIR',str(tmp_path))
    api.update_settings(api.SettingsUpdate(risk_pct_default=0.75,cooldown_minutes=17))
    assert config.load()['risk_pct_default']==0.75
    assert config.load_history()[0]['changes']
    with sqlite3.connect(test_db) as conn:
        original=conn.execute('SELECT count(*) FROM paper_positions').fetchone()[0]
        s=create_session(conn);ident=s['session_id']
    with sqlite3.connect(test_db) as conn:
        result=run_example(conn,ident)
    with sqlite3.connect(test_db) as conn:
        assert run_example(conn,ident)==result
        assert load_session(conn,ident).snapshot()['cash']==result['cash']
        assert conn.execute('SELECT count(*) FROM intelligence_virtual_events').fetchone()[0]==2
        assert conn.execute('SELECT count(*) FROM paper_positions').fetchone()[0]==original
    assert result['network_orders']==0 and result['telegram_mode']=='dry-run'


def test_neon_does_not_show_retired_render_expiry(monkeypatch):
    from sindhu_web.api import settings
    monkeypatch.setattr(settings.db_backend,'IS_POSTGRES',True)
    monkeypatch.setenv('DATABASE_URL','postgresql://synthetic.invalid@fixture.neon.tech/neondb')
    assert settings._postgres_expiry_notice({}) is None


def test_virtual_pause_resume_is_append_only_and_persists(test_db):
    from trading_intelligence.sessions import create_session,control_session,run_example,session_paused
    with sqlite3.connect(test_db) as conn:
        ident=create_session(conn)['session_id']
    with sqlite3.connect(test_db) as conn:
        assert control_session(conn,ident,True)['paused']
    with sqlite3.connect(test_db) as conn:
        assert session_paused(conn,ident)
        with pytest.raises(ValueError,match='paused'):
            run_example(conn,ident)
    with sqlite3.connect(test_db) as conn:
        assert not control_session(conn,ident,False)['paused']
    with sqlite3.connect(test_db) as conn:
        result=run_example(conn,ident)
    with sqlite3.connect(test_db) as conn:
        assert conn.execute('SELECT count(*) FROM intelligence_virtual_controls').fetchone()[0]==2
        assert run_example(conn,ident)==result


def test_journal_redaction_does_not_echo_credentials():
    from sindhu_web.api.quality import safe_text
    raw='postgresql://user:private@host/db password=private 123456789:abcdefghijklmnopqrstu token=private'
    assert 'private' not in safe_text(raw)


def live_frame():
    import pandas as pd
    index=pd.date_range('2026-10-10T18:00:00Z',periods=30,freq='1min')
    return pd.DataFrame({'open':100.,'high':102.,'low':99.,'close':101.,'volume':5.},index=index)


def test_market_guard_excludes_forming_bar_and_records_actual_close():
    from paper_trading.market_data_guard import closed_recent_frame
    frame=live_frame();now=int(frame.index[-1].timestamp()*1000)+30000
    closed,receipt=closed_recent_frame(frame,'1m',now)
    assert len(closed)==29 and receipt['age_ms']==30000
    assert receipt['last_closed_at_ms']==int(frame.index[-1].timestamp()*1000)
    assert len(frame)==30


@pytest.mark.parametrize('fault',['stale','future','duplicate','unordered','nan','bad_bounds','gap','negative_volume'])
def test_market_guard_rejects_unsafe_input(fault):
    import numpy as np
    from paper_trading.market_data_guard import closed_recent_frame,MarketDataRejected
    frame=live_frame();now=int(frame.index[-1].timestamp()*1000)+60000
    if fault=='stale':now+=120000
    elif fault=='future':now-=120000
    elif fault=='duplicate':frame.index=list(frame.index[:-1])+[frame.index[-2]]
    elif fault=='unordered':frame=frame.iloc[::-1]
    elif fault=='nan':frame.iloc[-1,0]=np.nan
    elif fault=='bad_bounds':frame.iloc[-1,1]=90
    elif fault=='gap':frame=frame.drop(frame.index[-3])
    elif fault=='negative_volume':frame.iloc[-1,4]=-1
    with pytest.raises(MarketDataRejected):closed_recent_frame(frame,'1m',now)


def test_private_telegram_dry_run_returns_before_network_or_credentials(monkeypatch):
    from paper_trading import telegram_bot
    monkeypatch.setenv('SINDHU_TELEGRAM_DRY_RUN','1')
    monkeypatch.setattr(telegram_bot,'load_settings',lambda:pytest.fail('Dry-run must not load credentials'))
    monkeypatch.setattr(telegram_bot.requests,'post',lambda *a,**k:pytest.fail('Network delivery forbidden'))
    ok,error=telegram_bot._raw_send('Synthetic private test',channel_id_override='synthetic-private')
    assert not ok and 'network delivery disabled' in error


def test_strategy_enable_pause_resume_and_settings_persist_in_isolation(test_db):
    from sindhu_web.api import paper_trading as api
    from data_engine import storage
    api.update_strategy_config('synthetic-only',api.StrategyConfigUpdate(enabled=True,priority=7))
    api.pause_strategy_manual('synthetic-only')
    assert storage.get_paper_strategy_config('synthetic-only')['enabled']
    assert storage.is_strategy_paused('synthetic-only')[0]
    api.resume_strategy_manual('synthetic-only')
    assert not storage.is_strategy_paused('synthetic-only')[0]
    assert storage.get_paper_strategy_config('synthetic-only')['priority']==7


def test_matcher_preserves_version_and_excludes_blocked_or_archived(monkeypatch):
    from paper_trading import strategy_matcher as matcher
    from data_engine import storage
    monkeypatch.setattr(storage,'list_paper_strategy_configs',lambda:{x:{'enabled':True,'priority':7} for x in ('good','blocked','archived')})
    monkeypatch.setattr(matcher.lib,'list_all_including_synced',lambda:[
        {'id':'good','name':'QA','current_version':3},
        {'id':'blocked','name':'QA','safety_status':'blocked'},
        {'id':'archived','name':'QA','archived':True}])
    monkeypatch.setattr(matcher.lib,'load_including_synced',lambda ident:object())
    rows=matcher.relevant_strategies('QA','ranging')
    assert len(rows)==1 and rows[0]['strategy_version']==3 and rows[0]['priority']==7


def test_signal_candidate_version_is_not_priority_and_stale_native_data_is_skipped(monkeypatch):
    from types import SimpleNamespace
    from paper_trading import signal_generator as generator
    frame=live_frame();now=int(frame.index[-1].timestamp())+60
    monkeypatch.setattr(generator.time,'time',lambda:now)
    class Context:
        def __init__(self,*a,**k):self.roles={'entry':'1m'};self.frames={'entry':frame.copy()}
        def is_empty(self):return False
    class Strategy:
        def __init__(self,cfg):pass
        def prepare_context(self,ctx):return ctx.frames['entry']
        def prepare(self,df):return df
        def on_bar(self,*a,**k):return SimpleNamespace(action='buy',stop_loss=99,take_profit=110,reason='Synthetic test')
    monkeypatch.setattr(generator,'MultiTimeframeContext',Context)
    monkeypatch.setattr(generator,'ConfiguredStrategy',Strategy)
    strategy={'strategy_id':'qa','strategy_name':'QA','strategy_version':3,'priority':7,
              'config':SimpleNamespace(timeframes={'entry':'1m'})}
    result=generator.strategy_candidates('synthetic','QA',[strategy],[],{})
    assert result[0]['strategy_version']==3
    now+=180
    settings={'_scan_diagnostics':[]}
    assert generator.strategy_candidates('synthetic','QA',[strategy],[],settings)==[]
    assert 'Stale' in settings['_scan_diagnostics'][0]


def test_legacy_leaderboard_version_provenance_is_explicit_without_rewriting():
    from trading_intelligence.leaderboard import leaderboard
    trade={'id':'legacy','strategy_id':'qa','strategy_version':7,'pnl':1,'closed_at':'2026-09-01'}
    result=leaderboard([trade],definitions=[])
    assert result['rows'][0]['version']==7 and trade['strategy_version']==7
    assert 'unverified' in result['rows'][0]['version_provenance']
