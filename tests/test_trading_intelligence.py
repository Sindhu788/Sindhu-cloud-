import json
import math
from pathlib import Path
import sqlite3

import pandas as pd
import pytest

from backtest_engine import concepts as c
from trading_intelligence.analysis import analyze, detect, Evidence, evaluate_evidence, position_size
from trading_intelligence.catalog import strategy_library, evaluate_existing_strategy
from trading_intelligence.curriculum import curriculum
from trading_intelligence.exam import run_exam
from trading_intelligence.leaderboard import metrics, leaderboard
from trading_intelligence.research import validate_candles, baseline_backtest, chronological_split, walk_forward, prefix_invariant, import_csv
from trading_intelligence.virtual import VirtualLedger, signal_key, claim_signal, dry_run_message


def candles(n=240):
    rows=[]
    for i in range(n):
        p=100+i*.02+math.sin(i/4)*3
        rows.append(dict(timestamp=1704067200000+i*3600000,open=p,high=p+1,low=p-1,close=p+.2,volume=100+i%7))
    return rows


@pytest.mark.parametrize('values,expected',[(list(range(60)),100),(list(range(60,0,-1)),0),([4]*60,50)])
def test_rsi_gain_loss_and_flat_boundaries(values,expected):
    assert c.rsi(pd.Series(values,dtype=float)).iloc[-1]==expected


def test_pivot_level_uses_pivot_price_and_only_after_confirmation():
    frame=pd.DataFrame({'high':[101,105,110,107,105], 'low':[99,103,108,105,103], 'close':[100,104,109,106,104]})
    _,resistance=c.support_resistance(frame)
    assert resistance.iloc[:4].isna().all()
    assert resistance.iloc[4]==110


@pytest.mark.parametrize('function',[c.support_resistance,c.break_of_structure,c.change_of_character,c.fair_value_gap,c.order_blocks,c.liquidity_sweep,c.rsi])
def test_no_future_information_changes_prefix(function):
    frame=validate_candles(candles())
    if function is c.rsi:frame=frame.close
    assert prefix_invariant(function,frame,[80,160,230])


@pytest.mark.parametrize('mutation',[
    lambda r:r[2].update(timestamp=r[1]['timestamp']),
    lambda r:r[2].update(timestamp=r[2]['timestamp']+1),
    lambda r:r[2].update(high=1),lambda r:r[2].update(volume=-1),
    lambda r:r[2].update(close=float('nan')),lambda r:r[2].update(open=True)])
def test_bad_candles_are_not_silently_repaired(mutation):
    rows=candles(4);mutation(rows)
    with pytest.raises(ValueError):validate_candles(rows)


def test_duplicate_correlated_indicators_never_inflate_vote():
    group=[Evidence(str(i),'trend','bullish') for i in range(50)]
    result=evaluate_evidence(group)
    assert result['decision']=='NO_TRADE' and len(result['families'])==1


def test_conflicts_and_invalidation_override_agreement():
    ev=[Evidence('ema','trend','bullish'),Evidence('volume','volume','bullish')]
    assert evaluate_evidence(ev)['decision']=='PAPER_CANDIDATE'
    assert evaluate_evidence(ev,invalidated=True)['decision']=='NO_TRADE'
    assert evaluate_evidence(ev+[Evidence('sweep','price_action','bearish')])['decision']=='NO_TRADE'
    weak=[Evidence('ema','trend','bullish',.1),Evidence('volume','volume','bullish',.2)]
    assert evaluate_evidence(weak)['decision']=='NO_TRADE'


def test_live_data_requires_closed_fresh_candle_and_unsupported_feeds_stay_missing():
    rows=candles(60)
    result=analyze(rows,data_label='live',as_of_ms=rows[-1]['timestamp'])
    assert result['decision']=='NO_TRADE' and result['execution_allowed'] is False
    assert 'open_interest' in result['unsupported_data']


def test_deterministic_independent_exam_has_no_failures():
    result=run_exam()
    assert result['total']>=60
    assert result['failures']==[]
    assert not result['profitability_tested']


def test_curriculum_maps_real_versioned_library_without_promotions():
    result=curriculum();library=strategy_library()
    assert len(result['modules'])==24 and len(library)>=154
    for module in result['modules']:
        assert all(module[k] for k in ('definition','detection_rules','required_data','confirmation','invalidation','limitations','worked_example','test_cases'))
    assert all(s.get('status')!='paper-approved' for s in library)
    assert len({s['id'] for s in library})==len(library)


@pytest.mark.parametrize('strategy_id',['143a732de079','2a7a1524c270'])
def test_existing_saved_strategy_runs_through_original_rule_engine(strategy_id):
    result=evaluate_existing_strategy(strategy_id,candles(240),'1h')
    assert result['execution_allowed'] is False
    assert result.get('strategy_id')==strategy_id
    assert result['decision'] in ('NO_TRADE','PAPER_CANDIDATE')


def test_costs_worsen_same_baseline_and_fills_are_next_bar():
    rows=candles()
    free=baseline_backtest(rows,fee_bps=0,slippage_bps=0)
    costed=baseline_backtest(rows,fee_bps=10,slippage_bps=5)
    assert costed['final_balance']<free['final_balance']
    assert free==baseline_backtest(rows,fee_bps=0,slippage_bps=0)
    for fill in free['fills']:
        assert fill['price']==rows[fill['bar']]['close' if fill.get('reason') else 'open']
    assert free['fills'][0]['bar']>=20


def test_splits_and_walk_forward_have_no_overlap_or_future_training():
    split=chronological_split(240)
    assert split['train'][1]<split['validation'][0]<split['validation'][1]<split['test'][0]
    for fold in walk_forward(240):assert fold['train'][1]<fold['test'][0]


def test_walk_forward_measures_unseen_windows_without_changing_training_selection():
    from trading_intelligence.research import walk_forward_evaluation,research_validation
    rows=candles(240)
    result=walk_forward_evaluation(rows,data_label='synthetic')
    changed=[dict(row) for row in rows]
    for row in changed[101:]:
        for key in ('open','high','low','close'):row[key]*=2
    second=walk_forward_evaluation(changed,data_label='synthetic')
    assert result['folds'][0]['train_trials']==second['folds'][0]['train_trials']
    assert result['folds'][0]['selected_period']==second['folds'][0]['selected_period']
    assert all(f['test']['data_label']=='synthetic' for f in result['folds'])
    assert research_validation(rows,data_label='synthetic')['test']['data_label']=='synthetic'


def test_migration_guard_never_overwrites_or_treats_a_retry_as_a_new_import():
    from trading_intelligence.migration_guard import import_decision
    args=dict(explicitly_approved=False,destination_empty=True,backup_valid=True,
              test_migration_valid=True,secrets_scan_valid=True,expected_payload_hash='a'*64)
    assert import_decision(**args)['action']=='AWAITING_EXPLICIT_APPROVAL'
    args['explicitly_approved']=True
    assert import_decision(**args)['write_allowed']
    args['destination_empty']=False
    assert not import_decision(**args)['write_allowed']
    assert import_decision(**args,receipt_payload_hash='a'*64,destination_integrity_matches=True)['action']=='NOOP_ALREADY_IMPORTED'
    assert import_decision(**args,receipt_payload_hash='a'*64,destination_integrity_matches=False)['action']=='REFUSE_EXISTING_OR_PARTIAL_DATA'


def test_csv_import_uses_same_strict_validation():
    frame=import_csv('timestamp,open,high,low,close,volume\n1704067200000,100,102,99,101,10\n')
    assert len(frame)==1


def test_leaderboard_uses_pnl_not_winrate_and_separates_versions():
    rows=[dict(id=str(i),strategy_id='x',strategy_name='Example',strategy_version=v,pnl=p,pnl_pct=p,closed_at=str(i),market_state='ranging')
          for i,(v,p) in enumerate([(1,2),(1,-5),(1,1),(2,10)])]
    result=leaderboard(rows,definitions=[])
    assert len(result['rows'])==2
    m=metrics(rows[:3]);assert m['profit_factor']==.6 and m['max_drawdown']==5
    assert m['expectancy']==pytest.approx(-2/3) and m['max_drawdown_pct'] is None
    assert m['status']=='REVIEW' and m['paper_approved'] is False


def test_undefined_no_loss_ratio_and_missing_pnl_are_not_invented():
    assert metrics([])['status']=='NOT TESTED'
    assert metrics([{'id':'1','pnl':1}])['profit_factor'] is None
    assert metrics([{'id':'2','pnl':None}])['trades']==0


def test_virtual_cash_fees_and_historical_isolation():
    ledger=VirtualLedger('test-only',100,data_label='synthetic')
    assert ledger.snapshot()['realized_pnl']==0
    ledger.open('qa-1',10,5,reason='Synthetic fixture',fee_bps=10)
    trade=ledger.close('qa-1',12,fee_bps=10)
    assert trade['pnl']==pytest.approx(9.89)
    assert ledger.balance==pytest.approx(109.89)
    assert ledger.snapshot()['open_positions']==0
    with pytest.raises(ValueError):ledger.open('qa-1',10,1,reason='duplicate')
    with pytest.raises(ValueError):VirtualLedger('legacy',100,data_label='synthetic')


def test_signal_claim_blocks_duplicate_and_wrong_publisher():
    conn=sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE intelligence_signal_claims(signal_key TEXT PRIMARY KEY,owner TEXT NOT NULL)')
    key=signal_key('test','strategy',1,'EXAMPLE',123,'bullish')
    assert not claim_signal(conn,key,'main',configured_owner='cloud')
    assert claim_signal(conn,key,'cloud',configured_owner='cloud')
    assert not claim_signal(conn,key,'cloud',configured_owner='cloud')
    assert conn.execute('SELECT count(*) FROM intelligence_signal_claims').fetchone()[0]==1


def test_main_cloud_public_sender_ownership_and_private_notifications():
    from paper_trading.signal_ownership import public_delivery_allowed
    settings={'channel_id':'public','personal_chat_id':'private'}
    assert not public_delivery_allowed(settings,'public',environ={})
    assert public_delivery_allowed(settings,'public',environ={'SINDHU_CLOUD_MODE':'1'})
    assert public_delivery_allowed(settings,'private',environ={})
    assert not public_delivery_allowed(settings,'strategy-channel',environ={})
    assert not public_delivery_allowed(settings,'public',environ={'SINDHU_PUBLIC_SIGNAL_OWNER':'invalid'})
    assert not public_delivery_allowed(settings,'public',environ={'SINDHU_PUBLIC_SIGNAL_OWNER':'main','SINDHU_CLOUD_MODE':'1'})


def test_non_owner_sender_returns_before_any_network_call(monkeypatch):
    from paper_trading import telegram_bot
    monkeypatch.delenv('SINDHU_TELEGRAM_DRY_RUN',raising=False)
    monkeypatch.delenv('SINDHU_CLOUD_MODE',raising=False)
    monkeypatch.delenv('SINDHU_PUBLIC_SIGNAL_OWNER',raising=False)
    monkeypatch.setattr(telegram_bot,'load_settings',lambda:{'channel_id':'public'})
    monkeypatch.setattr(telegram_bot.requests,'post',lambda *a,**k:pytest.fail('Unexpected network call'))
    ok,error=telegram_bot._raw_send('Synthetic QA message')
    assert not ok and 'publisher' in error


def test_dryrun_never_sends_and_escapes_html():
    msg=dry_run_message({'decision':'NO_TRADE','reasons':['<script>'],'data_label':'synthetic'})
    assert not msg['sent'] and msg['network_calls']==0 and '<script>' not in msg['text']


def test_sizing_includes_costs_and_cash_cap():
    risk=position_size(1000,100,98)
    assert risk['quantity']<5 and risk['planned_loss_including_assumed_costs']<=10.0000001


def test_api_contract_and_existing_auth_guard(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sindhu_web.api.intelligence import router
    from sindhu_web import security
    app=FastAPI();app.include_router(router)
    app.middleware('http')(security.token_guard_middleware)
    monkeypatch.setattr(security.auth,'is_valid_session',lambda value:value=='qa-session')
    monkeypatch.setattr(security,'get_or_create_token',lambda:'qa-csrf')
    client=TestClient(app,base_url='http://127.0.0.1',client=('127.0.0.1',50000))
    assert client.get('/api/intelligence/health').status_code==401
    client.cookies.set(security.auth.SESSION_COOKIE,'qa-session')
    assert client.get('/api/intelligence/health').json()['educational_only']
    assert client.get('/how-to-trade').status_code==200
    assert client.post('/api/intelligence/analyze',json={'candles':candles(60)}).status_code==401
    client.headers['X-Sindhu-Token']='qa-csrf'
    assert client.post('/api/intelligence/analyze',json={'candles':candles(60)}).status_code==200
    assert client.post('/api/intelligence/analyze',json={'candles':[]}).status_code==422
    assert client.post('/api/intelligence/exam',json={}).json()['failures']==[]


def test_main_cloud_mount_same_versioned_router():
    import sindhu_web.server as main
    import cloud_runtime.app as cloud
    for app in (main.app,cloud.app):
        paths=set(app.openapi()['paths'])
        assert '/api/intelligence/curriculum' in paths and '/how-to-trade' in paths


def test_actual_main_cloud_api_qa_with_lifespan_off(monkeypatch):
    from fastapi.testclient import TestClient
    import sindhu_web.server as main
    import cloud_runtime.app as cloud
    from sindhu_web import security
    monkeypatch.setattr(security.auth,'is_valid_session',lambda value:value=='isolated-qa-session')
    monkeypatch.setattr(security,'get_or_create_token',lambda:'isolated-qa-csrf')
    versions=[]
    # Deliberately no `with TestClient`: engines/schedulers must stay stopped.
    for app in (main.app,cloud.app):
        client=TestClient(app,base_url='http://127.0.0.1',client=('127.0.0.1',50000))
        client.cookies.set(security.auth.SESSION_COOKIE,'isolated-qa-session')
        client.headers['X-Sindhu-Token']='isolated-qa-csrf'
        assert client.get('/how-to-trade').status_code==200
        health=client.get('/api/intelligence/health').json()
        assert health['status']=='ok';versions.append(health['version'])
        assert len(client.get('/api/intelligence/curriculum').json()['modules'])==24
        payload={'candles':candles(240),'data_label':'synthetic'}
        analyzed=client.post('/api/intelligence/analyze',json=payload)
        assert analyzed.status_code==200 and analyzed.json()['execution_allowed'] is False
        assert not analyzed.json()['telegram_preview']['sent']
        research=client.post('/api/intelligence/research/evaluate',json=payload)
        assert research.status_code==200 and research.json()['walk_forward']['folds']
        assert client.post('/api/intelligence/strategy/does-not-exist/evaluate',json=payload).status_code==404
        assert client.get('/api/intelligence/leaderboard').status_code==200
    assert versions==['1.0.0','1.0.0']
