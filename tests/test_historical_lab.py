import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from trading_intelligence.historical_lab import derive_validate,metrics,verified_manifest


@pytest.mark.parametrize('tf',['5m','15m','30m','1h','4h','1d','1w','1M'])
def test_derived_candles_match_independent_source_math(tf):
    index=pd.date_range('2026-01-29',periods=40*1440,freq='min',tz='UTC')
    close=100+np.arange(len(index))*.0001
    frame=pd.DataFrame(dict(open=close,high=close+2,low=close-1,close=close+.1,volume=2.),index=index)
    result,receipt=derive_validate(frame,tf)
    assert receipt['validation']=='PASS' and len(result)>0
    assert np.isclose(result.volume.sum(),receipt['complete_source_minutes']*2)
    assert (result.high>=result.close).all()
    if tf=='1M':
        assert list(result.index)==[pd.Timestamp('2026-02-01',tz='UTC')]
        assert result.volume.iloc[0]==28*1440*2
    if tf=='1w':assert (result.index.weekday==0).all()


def test_derived_candles_refuse_a_hidden_source_gap():
    index=pd.date_range('2026-01-01',periods=20,freq='min',tz='UTC').delete(7)
    frame=pd.DataFrame(dict(open=10.,high=11.,low=9.,close=10.,volume=1.),index=index)
    with pytest.raises(ValueError,match='consecutive'):derive_validate(frame,'5m')


def test_partial_fills_are_one_trade_and_original_risk_is_used():
    trades=[dict(entry_time=1,side='long',pnl=2,initial_risk_amount=5,initial_planned_rr=2),
            dict(entry_time=1,side='long',pnl=3,initial_risk_amount=5,initial_planned_rr=2),
            dict(entry_time=2,side='long',pnl=-10,initial_risk_amount=10,initial_planned_rr=2)]
    result=metrics(trades,[1000,1005,995])
    assert result['sample_size']==2 and result['win_rate_pct']==50
    assert result['net_expectancy_r']==-.25 and result['profit_factor']==.5
    assert result['average_winning_r']==.5 and result['average_losing_r']==-1
    assert np.isclose(result['max_drawdown_pct'],10/1005*100)


def test_zero_trades_does_not_invent_a_zero_win_rate():
    result=metrics([],[])
    assert result['win_rate_pct'] is None and result['profit_factor'] is None


def test_full_recheck_is_mandatory(tmp_path):
    (tmp_path/'manifest.json').write_text('{}')
    with pytest.raises(ValueError,match='finish'):verified_manifest(tmp_path)
    (tmp_path/'verification.json').write_text(json.dumps({'complete':True,'records_verified':5256000,'manifest_sha256':'wrong'}))
    with pytest.raises(ValueError,match='invalid'):verified_manifest(tmp_path)


def test_replication_selection_cannot_read_holdout_results():
    from copy import deepcopy
    from trading_intelligence.historical_lab import replication_selection
    rows=[{'strategy_id':str(i),'leakage_audit':{'pass':True},'results':{'train':{'sample_size':40},'validation':{'sample_size':40,'expectancy_r_week_block95':[i/100,1]},'holdout':{'net_expectancy_r':i}}} for i in range(7)]
    expected=replication_selection(rows)
    modified=deepcopy(rows)
    for row in modified:row['results']['holdout']['net_expectancy_r']=-10000*int(row['strategy_id'])
    assert replication_selection(modified)==expected==['6','5','4','3','2']


def test_reused_prepared_features_match_original_replay():
    from trading_intelligence.catalog import load_strategy_config
    from trading_intelligence.historical_lab import prepared,replay
    index=pd.date_range('2026-01-01',periods=350,freq='h',tz='UTC');close=100+np.sin(np.arange(350)/7)*3
    frame=pd.DataFrame(dict(open=close,high=close+1,low=close-1,close=close+.1,volume=100.),index=index)
    config=load_strategy_config('143a732de079');frames={'1h':frame};start=index[220];end=index[-1]+pd.Timedelta(hours=1)
    expected,trades=replay(config,frames,start,end)
    actual,other=replay(config,frames,start,end,prepared_frame=prepared(config,frames)[1])
    assert trades==other and expected==actual


def test_lab_endpoint_is_read_only_and_ranks_without_holdout(tmp_path,monkeypatch):
    from data_engine import paths
    from sindhu_web.api.intelligence import historical_lab
    monkeypatch.setattr(paths,'DATA_DIR',str(tmp_path))
    assert historical_lab()['status']=='UNAVAILABLE'
    root=tmp_path/'research_lab';run_id='a'*20;(root/run_id).mkdir(parents=True)
    (root/'progress.json').write_text(json.dumps({'run_id':run_id,'stage':'frozen_rule_replay'}))
    for ident,score,holdout in [('one',.2,-100),('two',-.1,100)]:
        (root/run_id/('BTC-'+ident+'.json')).write_text(json.dumps({'strategy_id':ident,'policy_quarantined':False,'leakage_audit':{'pass':True},'results':{'validation':{'sample_size':40,'expectancy_r_week_block95':[score,1]},'holdout':{'net_expectancy_r':holdout}}}))
    (root/run_id/'BTC-leaky.json').write_text(json.dumps({'strategy_id':'leaky','policy_quarantined':False,'leakage_audit':{'pass':False},'results':{'validation':{'sample_size':400,'expectancy_r_week_block95':[100,101]}}}))
    result=historical_lab(1)
    assert result['completed_cases']==3 and len(result['rows'])==1
    assert result['rows'][0]['strategy_id']=='one' and result['automatic_approval'] is False


def test_real_engine_preserves_original_risk_after_trailing_stop():
    from backtest_engine.engine import run_backtest
    from strategies.base import Signal,Strategy as BaseStrategy
    class Strategy(BaseStrategy):
        config=SimpleNamespace(stop_loss=SimpleNamespace(type='fixed_pct'),entry_type='market')
        def prepare(self,df):return df
        def on_bar(self,df,i,position):return Signal('buy',stop_loss=90,take_profit=130) if i==0 else None
        def manage_position(self,df,i,position):
            if i==1:position['stop_loss']=105
    frame=pd.DataFrame(dict(open=[100,110,115],high=[100,120,116],low=[100,105,100],close=[100,115,105]),index=pd.date_range('2026-01-01',periods=3,freq='h'))
    trades,_,_=run_backtest(frame,Strategy(),{'initial_balance':1000,'risk_pct':1})
    assert trades and trades[0]['initial_risk_amount']>0
    assert trades[0]['initial_risk_amount']==10 and trades[0]['risk_amount']==5
    assert trades[0]['initial_planned_rr']==3
