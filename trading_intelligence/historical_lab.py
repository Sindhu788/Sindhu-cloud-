"""Offline, frozen-rule research. No storage credentials, broker or notifications.

The verified archive is immutable. Derived arrays and machine results are local
research checkpoints, never written into the trading database.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time

import numpy as np
import pandas as pd

from market_history.core import archive_rows, sha256
from market_history.downloader import COINS, atomic_json

TIMEFRAMES = ('5m','15m','30m','1h','4h','1d','1w','1M')
RULES = {'1m':'1min','5m':'5min','15m':'15min','30m':'30min','1h':'1h',
         '4h':'4h','1d':'1D','1w':'W-MON','1M':'MS'}
FIELDS = ('open','high','low','close','volume')
COSTS = dict(initial_balance=1000., commission_pct=.1, slippage_pct=.05,
             spread_pct=.02, risk_pct=.5, position_size_pct=10., leverage=1.)


def verified_manifest(root):
    root=Path(root); manifest=root/'manifest.json'; receipt=root/'verification.json'
    if not receipt.exists():raise ValueError('Full integrity recheck must finish before historical research.')
    value=json.loads(receipt.read_text())
    if not value.get('complete') or value.get('records_verified')!=5_256_000 or value.get('manifest_sha256')!=sha256(manifest):
        raise ValueError('Full integrity checkpoint is invalid or does not match the manifest.')
    return json.loads(manifest.read_text()),value


def load_source(root,coin,manifest):
    """Use checksummed source CSVs; the full receipt proves Parquet equivalence."""
    parts=sorted((p for k,p in manifest['partitions'].items() if k.startswith(coin+'/')),key=lambda p:p['start'])
    size=sum((p['end']-p['start'])//60000 for p in parts)
    stamps=np.empty(size,dtype=np.int64);values=np.empty((size,5),dtype=np.float64);i=0
    for part in parts:
        for name,digest in sorted(part['source_sha256'].items()):
            path=Path(root)/'raw'/coin/name
            if sha256(path)!=digest:raise ValueError('Source archive checksum changed: '+coin+'/'+name)
            for row in archive_rows(path,part['start'],part['end']):
                if i>=size:raise ValueError('Unexpected source row count.')
                stamps[i]=row['timestamp'];values[i]=[row[k] for k in FIELDS];i+=1
    if i!=size or (np.diff(stamps)!=60000).any():raise ValueError('Source ordering, gaps or count failed.')
    return pd.DataFrame(values,index=pd.to_datetime(stamps,unit='ms',utc=True),columns=FIELDS)


def derive_validate(source,timeframe):
    """Compare pandas resampling to independent numpy boundary/reduction math."""
    if timeframe not in TIMEFRAMES:raise ValueError('Unsupported derived timeframe.')
    source=source.copy(deep=False);source.index=source.index.as_unit('ns')
    index=source.index;ms=index.asi8//1_000_000
    if source.empty or (np.diff(ms)!=60000).any():raise ValueError('Derived input must be consecutive original 1m candles.')
    if timeframe=='1M':
        labels=pd.DatetimeIndex([datetime(y,m,1,tzinfo=timezone.utc) for y,m in zip(index.year,index.month)])
        ends=labels+pd.offsets.MonthBegin(1)
    elif timeframe=='1w':
        labels=index.normalize()-pd.to_timedelta(index.weekday,unit='D');ends=labels+pd.Timedelta(days=7)
    else:
        step=pd.Timedelta(RULES[timeframe]).value//1_000_000
        labels=pd.to_datetime(ms//step*step,unit='ms',utc=True);ends=labels+pd.Timedelta(milliseconds=step)
    labels=labels.as_unit('ns');ends=ends.as_unit('ns')
    starts=np.r_[0,np.flatnonzero(np.diff(labels.asi8))+1];last=np.r_[starts[1:]-1,len(source)-1]
    expected=((ends.asi8-labels.asi8)//60_000_000_000)[starts]
    keep=(last-starts+1==expected)&(ms[starts]==labels.asi8[starts]//1_000_000)&(ms[last]+60000==ends.asi8[starts]//1_000_000)
    values=source.to_numpy();out=np.column_stack((values[starts,0],np.maximum.reduceat(values[:,1],starts),
          np.minimum.reduceat(values[:,2],starts),values[last,3],np.add.reduceat(values[:,4],starts)))
    independent=pd.DataFrame(out[keep],index=labels[starts[keep]],columns=FIELDS)
    aggregate=source.resample(RULES[timeframe],label='left',closed='left').agg(
        dict(open='first',high='max',low='min',close='last',volume='sum'))
    aggregate=aggregate.loc[independent.index]
    if not np.allclose(independent.to_numpy(),aggregate.to_numpy(),rtol=1e-11,atol=1e-8):
        raise ValueError('Derived candle/source mismatch: '+timeframe)
    return aggregate,{'timeframe':timeframe,'bars':len(aggregate),'complete_source_minutes':int(expected[keep].sum()),
                      'partial_edge_buckets_omitted':int((~keep).sum()),'validation':'PASS'}


def metrics(trades,equity,initial=1000.):
    """Partial fills count once per position; R uses original, untrailed risk."""
    episodes=defaultdict(list)
    for t in trades:episodes[(t['entry_time'],t['side'])].append(t)
    pnl=[];rs=[];planned=[];sides=Counter();weekly=defaultdict(lambda:[0.,0])
    for parts in episodes.values():
        amount=sum(t['pnl'] for t in parts);risk=sum(t.get('initial_risk_amount',0) for t in parts)
        pnl.append(amount);sides[parts[0]['side']]+=1
        if risk>0:
            realized=amount/risk;rs.append(realized)
            week=parts[0]['entry_time']//(7*86400000);weekly[week][0]+=realized;weekly[week][1]+=1
        rr=parts[0].get('initial_planned_rr')
        if rr is not None:planned.append(rr)
    n=len(pnl);wins=sum(x>0 for x in pnl);positive=sum(max(x,0) for x in pnl);negative=-sum(min(x,0) for x in pnl)
    peak=initial;drawdown=0.
    for value in equity:peak=max(peak,value);drawdown=max(drawdown,(peak-value)/peak*100)
    if n:
        p=wins/n;z=1.96;den=1+z*z/n;centre=(p+z*z/(2*n))/den
        half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den;ci=[100*(centre-half),100*(centre+half)]
    else:ci=None
    block_ci=None
    if len(weekly)>=4:
        blocks=np.array([weekly[w] for w in range(min(weekly),max(weekly)+1)])
        sample=np.random.default_rng(0).integers(0,len(blocks),size=(1000,len(blocks)))
        totals=blocks[sample].sum(axis=1);means=totals[totals[:,1]>0,0]/totals[totals[:,1]>0,1]
        block_ci=np.quantile(means,[.025,.975]).tolist()
    return {'sample_size':n,'win_rate_pct':wins/n*100 if n else None,'win_rate_wilson95_pct':ci,
            'planned_rr_mean':float(np.mean(planned)) if planned else None,
            'realized_average_r':float(np.mean(rs)) if rs else None,
            'average_winning_r':float(np.mean([x for x in rs if x>0])) if any(x>0 for x in rs) else None,
            'average_losing_r':float(np.mean([x for x in rs if x<=0])) if any(x<=0 for x in rs) else None,
            'net_expectancy_dollars':sum(pnl)/n if n else None,
            'net_expectancy_r':float(np.mean(rs)) if rs else None,
            'expectancy_r_week_block95':block_ci,
            'profit_factor':positive/negative if negative else None,'max_drawdown_pct':drawdown,
            'net_profit_dollars':sum(pnl),'side_counts':dict(sides),
            'uncertainty':'Wilson assumes independent trades; weekly block bootstrap is heuristic. Long dependence and 154 hypotheses weaken inference.'}


def prepared(config,frames,end=None):
    from backtest_engine.configured_strategy import ConfiguredStrategy
    from backtest_engine.mtf_context import MultiTimeframeContext
    roles=config.timeframes or {'entry':'1h'}
    native={role:frames[tf].loc[:end].copy() if end is not None else frames[tf].copy() for role,tf in roles.items()}
    strategy=ConfiguredStrategy(deepcopy(config))
    frame=strategy.prepare_context(MultiTimeframeContext.from_frames(native,roles))
    return strategy,strategy.prepare(frame)


def leakage_check(config,frames,full_prepared=None):
    """Future appends may not change prepared features or sampled decisions."""
    strategy,full=full_prepared or prepared(config,frames)
    for cut in (max(3,len(full)//3),max(4,len(full)*2//3)):
        if cut>=len(full):continue
        prefix_strategy,prefix=prepared(config,frames,full.index[cut-1])
        a=full.iloc[:cut];b=prefix.reindex(a.index)
        if list(a.columns)!=list(b.columns):return False,'Prepared feature columns changed.'
        try:pd.testing.assert_frame_equal(a,b,check_exact=False,rtol=1e-10,atol=1e-10,check_freq=False)
        except AssertionError:return False,'Future appends changed past prepared features.'
        for i in (max(0,cut-3),cut-1):
            sa=strategy.on_bar(full,i,None);sb=prefix_strategy.on_bar(prefix,i,None)
            if (vars(sa) if sa else None)!=(vars(sb) if sb else None):return False,'Future appends changed a past signal.'
    return True,'Two chronological feature prefixes and sampled signals match; not a proof for every possible input.'


class FrozenReplay:
    def __init__(self,strategy,frame,start,end,spot_only):
        self.inner=strategy;self.config=strategy.config;self.frame=frame;self.start=start;self.end=end;self.spot_only=spot_only
        self.active=(frame.index>=start)&(frame.index<end)
    def prepare(self,frame):return self.frame
    def manage_position(self,frame,i,position):return self.inner.manage_position(frame,i,position)
    def on_bar(self,frame,i,position):
        if not self.active[i]:return None
        signal=self.inner.on_bar(frame,i,position)
        if self.spot_only and signal is not None and signal.action=='sell':return None
        return signal


class TimeBudget:
    def __init__(self,seconds):self.until=time.monotonic()+seconds;self.expired=False
    def should_stop(self):
        self.expired=time.monotonic()>self.until
        return self.expired


def replay(config,frames,start,end,*,spot_only=True,seconds=120,prepared_frame=None):
    from backtest_engine.engine import run_backtest
    # Fills after a completed signal bar, never at its already-known close.
    cfg=deepcopy(config)
    if cfg.entry_type in ('market','current_candle_close'):cfg.entry_type='next_candle_open'
    for name in ('long_entry_type','short_entry_type'):
        if getattr(cfg,name,None) in ('market','current_candle_close'):setattr(cfg,name,'next_candle_open')
    if prepared_frame is None:strategy,frame=prepared(cfg,frames,end)
    else:
        from backtest_engine.configured_strategy import ConfiguredStrategy
        strategy=ConfiguredStrategy(cfg);strategy._arr_cache={};frame=prepared_frame
    # Include at most 250 earlier entry bars for warmup; native higher roles
    # retain their own history. Force the final liquidation inside this split.
    eligible=np.flatnonzero((frame.index>=start)&(frame.index<end))
    if len(eligible)<2:raise ValueError('Insufficient evaluation candles.')
    frame=frame.iloc[max(0,eligible[0]-250):eligible[-1]+1].copy()
    if prepared_frame is None:strategy.prepare(frame)
    wrapper=FrozenReplay(strategy,frame,start,end,spot_only);control=TimeBudget(seconds)
    trades,equity,balance=run_backtest(frame,wrapper,COSTS,control=control)
    if control.expired:raise TimeoutError('Replay time budget exhausted; partial results rejected.')
    return metrics(trades,equity),trades


def regime_labels(frame):
    from backtest_engine import concepts as c
    atr=c.atr(frame,14)/frame.close;spread=(c.ema(frame.close,20)-c.ema(frame.close,50)).abs()/frame.close
    return pd.Series(np.where(atr>=.03,'volatile',np.where(spread>=.005,'trending','ranging')),index=frame.index).where(np.arange(len(frame))>=50,'warmup')


def run_case(item,config,frames,coin,*,audit=True):
    from backtest_engine.validator import validate
    row={'strategy_id':item['id'],'name':item.get('name'),'version':item['version'],'definition_sha256':item['definition_sha256'],
         'coin':coin,'timeframe':config.timeframes.get('entry','1h'),'policy_quarantined':bool(item.get('archived') or item.get('status')=='rejected'),
         'costs':COSTS,'execution':'Spot long/flat, next-open market fills, SL-first intrabar ambiguity; no funding or borrow model.',
         'status':'NOT_TESTABLE','automatic_approval':False}
    errors=validate(config)
    if errors:row['reason']='; '.join(errors);return row
    for role,tf in config.timeframes.items():
        if tf not in frames or len(frames[tf])<200:
            row.update(status='INSUFFICIENT_DATA',reason='Fewer than 200 native warmup bars: '+role+'/'+tf);return row
    full_prepared=prepared(config,frames)
    if audit:
        passed,reason=leakage_check(config,frames,full_prepared)
        row['leakage_audit']={'pass':passed,'scope':reason}
        if not passed:row.update(status='QUARANTINED_LEAKAGE',reason=reason);return row
    entry=frames[row['timeframe']];first=entry.index[0];end=entry.index[-1]+pd.Timedelta(RULES[row['timeframe']])
    duration=end-first;a=first+duration*.6;b=first+duration*.8
    # One full entry-bar embargo separates split labels; no parameters selected.
    embargo=pd.Timedelta(RULES[row['timeframe']])
    windows={'train':(first,a),'validation':(a+embargo,b),'holdout':(b+embargo,end)}
    results={};holdout_trades=[]
    for split,(start,finish) in windows.items():
        result,trades=replay(config,frames,start,finish,prepared_frame=full_prepared[1])
        results[split]=result
        if split=='holdout':holdout_trades=trades
    labels=regime_labels(entry);by_regime={}
    for regime in ('trending','ranging','volatile','warmup'):
        subset=[t for t in holdout_trades if labels.asof(pd.Timestamp(t['entry_time'],unit='ms',tz='UTC'))==regime]
        by_regime[regime]=metrics(subset,[])
        by_regime[regime]['max_drawdown_pct']=None # A filtered subset has no standalone mark-to-market path.
    folds=[]
    for l,r in ((.4,.6),(.6,.8)):
        result=results['validation'] if l==.6 else replay(config,frames,first+duration*l+embargo,first+duration*r,prepared_frame=full_prepared[1])[0]
        folds.append({'fraction':[l,r],'metrics':result})
    row.update(status='RESEARCH_ONLY' if results['holdout']['sample_size']>=30 else 'INSUFFICIENT_SAMPLE',
               splits={k:[str(x),str(y)] for k,(x,y) in windows.items()},results=results,holdout_regimes=by_regime,
               walk_forward={'frozen_parameters':True,'folds':folds,'selection':'No fitting or optimization; chronological forward evaluation.'})
    return row


def curriculum_coverage():
    from trading_intelligence.curriculum import curriculum
    return [{'id':m['id'],'title':m['title'],'mode':m['mode'],'linked_definitions':len(m['strategy_ids']),
             'status':'REQUIRES_EXTERNAL_DATA' if m['mode']=='requires_external_data' else 'EDUCATIONAL_ONLY' if m['mode']=='interpretive' else 'EXECUTABLE_RULES_OR_POLICY'} for m in curriculum()['modules']]


def run_lab(root,output,coins=None):
    from trading_intelligence.catalog import strategy_library,load_strategy_config
    root=Path(root);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    manifest,receipt=verified_manifest(root);items=strategy_library();all_results=[];derived=[]
    identity={'manifest_sha256':receipt['manifest_sha256'],'definitions':{x['id']:x.get('definition_sha256') for x in items},'costs':COSTS,
              'protocol':'frozen-60-20-20-next-open-spot-v2-btc-library-five-validation-replications',
              'lab_sha256':sha256(Path(__file__)),'engine_sha256':sha256(Path(__file__).resolve().parents[1]/'backtest_engine/engine.py')}
    run_id=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:20]
    run_dir=output/run_id;run_dir.mkdir(exist_ok=True)
    selections=[]
    for coin in coins or COINS:
        completed=run_dir/(coin+'.json')
        if completed.exists():
            saved=json.loads(completed.read_text());all_results.extend(saved['results']);derived.extend(saved['derived'])
            if coin=='BTCUSDT':selections=replication_selection(saved['results'])
            continue
        atomic_json(output/'progress.json',{'run_id':run_id,'coin':coin,'stage':'source_validation','completed_cases':len(all_results)})
        source=load_source(root,coin,manifest);frames={'1m':source};coin_derived=[]
        for tf in TIMEFRAMES:
            frames[tf],check=derive_validate(source,tf);check['coin']=coin;coin_derived.append(check)
        coin_results=[]
        selected_items=items if coin=='BTCUSDT' else [x for x in items if x['id'] in selections]
        for item in selected_items:
            atomic_json(output/'progress.json',{'run_id':run_id,'coin':coin,'strategy_id':item['id'],'stage':'frozen_rule_replay','completed_cases':len(all_results)+len(coin_results)})
            case_path=run_dir/(coin+'-'+item['id']+'.json')
            if case_path.exists():row=json.loads(case_path.read_text())
            else:
                try:row=run_case(item,load_strategy_config(item['id']),frames,coin)
                except Exception as exc:row={'strategy_id':item['id'],'coin':coin,'status':'NOT_TESTABLE','reason':type(exc).__name__+': '+str(exc)[:250]}
                atomic_json(case_path,row)
            coin_results.append(row)
        if coin=='BTCUSDT':selections=replication_selection(coin_results)
        atomic_json(completed,{'identity':identity,'coin':coin,'derived':coin_derived,'results':coin_results})
        all_results.extend(coin_results);derived.extend(coin_derived)
    result={'run_id':run_id,'dataset':receipt,'identity':identity,'derived':derived,'curriculum':curriculum_coverage(),
            'counts':dict(Counter(r['status'] for r in all_results)),'strategy_definitions':len(items),'coin_cases':len(all_results),
            'results':all_results,'replication_selection':selections,'completed_at':datetime.now(timezone.utc).isoformat(),
            'limitations':['One year only; weekly/monthly statistical history insufficient.','Spot long/flat results do not validate hypothetical shorts.',
                           'Costs are explicit assumptions, not venue quotes.','No optimization on holdout; all trials retained, no automatic approval.']}
    atomic_json(output/'latest.json',result);atomic_json(output/'progress.json',{'run_id':run_id,'stage':'COMPLETED','coin_cases':len(all_results)})
    return result


def replication_selection(results):
    """Predeclared selection reads training/validation only, never holdout."""
    eligible=[r for r in results if not r.get('policy_quarantined') and r.get('leakage_audit',{}).get('pass')
              and r.get('results',{}).get('train',{}).get('sample_size',0)>=30
              and r.get('results',{}).get('validation',{}).get('sample_size',0)>=30]
    eligible.sort(key=lambda r:((r['results']['validation'].get('expectancy_r_week_block95') or [-1e9])[0],
                                r['results']['validation']['sample_size']),reverse=True)
    return [r['strategy_id'] for r in eligible[:5]]
