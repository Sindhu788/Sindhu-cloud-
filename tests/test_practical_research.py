import json,math
from pathlib import Path
import pandas as pd
import pytest
from trading_intelligence.research import validate_candles,baseline_backtest,research_validation,prefix_invariant
from trading_intelligence.practical import closed_trend_context,multi_timeframe_decision,structure_events,false_breakouts

def rows(n=240,step=3600000,direction=1):
    out=[]
    for i in range(n):
        price=100+direction*i*.03+math.sin(i/5)
        out.append(dict(timestamp=1767225600000+i*step,open=price-.1,high=price+1,low=price-1,close=price,volume=100+i%9))
    return out

def test_new_frozen_practical_exam():
    from trading_intelligence.practical_exam import run_exam
    result=run_exam()
    assert result['tests']==165
    assert result['failed']==[] and result['false_positive']==result['false_negative']==0

@pytest.mark.parametrize('n',[1,3,8,13])
def test_insufficient_warmup_is_no_trade_not_exception(n):
    from trading_intelligence.analysis import analyze
    result=analyze(rows(n));assert result['decision']=='NO_TRADE'
    assert result['regime']=='NOT TESTED' and not result['execution_allowed']

def test_gapped_break_cannot_be_its_own_order_block():
    from backtest_engine.concepts import order_blocks
    case=next(c for c in json.loads((Path(__file__).parents[1]/'trading_intelligence/fixtures/practical_inputs.json').read_text()) if c['id']=='order-block-origin-before-break-2')
    frame=validate_candles(case['candles']);low=order_blocks(frame)[0].iloc[-1]
    assert low==pytest.approx(frame.low.iloc[-2]) and low!=frame.low.iloc[-1]

def test_htf_open_bar_is_not_visible_until_native_close():
    lower=rows(12);higher=rows(4,4*3600000)
    context=closed_trend_context(lower,higher,period=2)
    assert pd.isna(context.iloc[2].higher_close)
    assert context.iloc[3].higher_close==higher[0]['close']
    assert context.iloc[6].higher_close==higher[0]['close']
    assert context.iloc[7].higher_close==higher[1]['close']
    assert (context.available_at.dropna()<=context.loc[context.available_at.notna(),'decision_at']).all()

def test_future_htf_mutation_does_not_change_available_context():
    lower=rows(6);higher=rows(4,4*3600000)
    first=closed_trend_context(lower,higher,period=2)
    for item in higher[1:]:item.update(open=900.,high=1000.,low=800.,close=950.)
    pd.testing.assert_frame_equal(first,closed_trend_context(lower,higher,period=2))

def test_mtf_conflict_and_missing_context_abstain():
    lower=rows(90,direction=1);higher=rows(25,4*3600000,direction=-1)
    # Monotone opposed trends, not oscillating series whose final slopes vary.
    for candles,sign in [(lower,1),(higher,-1)]:
        for i,candle in enumerate(candles):
            price=200+sign*i
            candle.update(open=price,high=price+1,low=price-1,close=price)
    assert multi_timeframe_decision(lower,higher)['decision']=='NO_TRADE'
    assert multi_timeframe_decision(lower[:3],higher)['decision']=='NO_TRADE'
    assert not multi_timeframe_decision(lower,higher)['execution_allowed']

@pytest.mark.parametrize('function',[structure_events,false_breakouts])
def test_added_detectors_are_prefix_invariant(function):
    assert prefix_invariant(function,validate_candles(rows()),[50,120,200])

def test_actual_native_context_does_not_expose_current_four_hour_candle():
    from backtest_engine.mtf_context import MultiTimeframeContext
    context=MultiTimeframeContext.from_frames({'entry':validate_candles(rows(12)), 'bias':validate_candles(rows(4,4*3600000),'4h')},{'entry':'1h','bias':'4h'})
    merged=context.build()
    assert pd.isna(merged.bias_close.iloc[3])
    assert merged.bias_close.iloc[4]==context.frames['bias'].close.iloc[0]

def test_research_fills_are_unique_next_open_and_costed():
    candles=rows()
    result=baseline_backtest(candles,period=5,data_label='synthetic')
    fills=result['fills'];assert fills and len({(r['bar'],r['side']) for r in fills})==len(fills)
    assert all(a['side']!=b['side'] for a,b in zip(fills,fills[1:]))
    first=fills[0];assert first['bar']>=5 and first['price']==pytest.approx(candles[first['bar']]['open']*1.0005)
    free=baseline_backtest(candles,period=5,fee_bps=0,slippage_bps=0,data_label='synthetic')
    assert result['final_balance']<free['final_balance']

def test_training_selection_is_unchanged_by_future_test_prices():
    candles=rows();first=research_validation(candles,data_label='synthetic')
    start=first['splits']['test'][0]
    for candle in candles[start:]:
        for key in ('open','high','low','close'):candle[key]*=2
    second=research_validation(candles,data_label='synthetic')
    assert first['selected_period']==second['selected_period'] and first['train_trials']==second['train_trials']

def test_leaderboard_reports_real_average_win_loss_and_unknowns():
    from trading_intelligence.leaderboard import metrics
    trades=[{'id':str(i),'closed_at':str(i),'pnl':value} for i,value in enumerate([10,20,-5,0])]
    result=metrics(trades)
    assert result['average_win']==15 and result['average_loss']==-5 and result['expectancy']==6.25
    assert 'independent backtest NOT TESTED' in result['validation_status']
    assert metrics([])['average_win'] is None and metrics([])['validation_status']=='NOT TESTED'

def test_partial_history_cannot_enter_full_backtest(tmp_path):
    from market_history.core import read_coin
    (tmp_path/'manifest.json').write_text(json.dumps({'partitions':{}}))
    with pytest.raises(ValueError,match='incomplete'):next(read_coin(tmp_path,'BTCUSDT'))

def test_finished_partition_tampering_is_not_silently_overwritten(tmp_path):
    from market_history.downloader import Download,START,END
    path=tmp_path/'final.parquet';path.write_bytes(b'tampered')
    (tmp_path/'manifest.json').write_text(json.dumps({'start':START,'end':END,'partitions':{'BTCUSDT/2025-11':{'complete':True,'path':path.name,'parquet_sha256':'wrong'}},'missing_archives':[]}))
    with pytest.raises(ValueError,match='checksum mismatch'):Download(tmp_path).partition('BTCUSDT','2025-11',START,END)
    assert path.read_bytes()==b'tampered'
