"""Unseen archive scenarios with mechanical labels, not expert profitability labels."""
from collections import Counter
import json
from pathlib import Path
import numpy as np
import pandas as pd

from market_history.core import archive_rows,sha256
from market_history.downloader import COINS,atomic_json
from trading_intelligence.historical_lab import verified_manifest,derive_validate


def evaluate_window(frame):
    from trading_intelligence.analysis import analyze,position_size
    from trading_intelligence.practical import false_breakouts
    rows=[dict(timestamp=int(t.timestamp()*1000),**{k:float(v) for k,v in row.items()}) for t,row in frame.iterrows()]
    result=analyze(rows,'1h','historical');last=frame.iloc[-1];prior=frame.iloc[-21:-1]
    low=float(prior.low.min());high=float(prior.high.max())
    expected_up=last.high>high and low<=last.close<=high
    expected_down=last.low<low and low<=last.close<=high
    up,down=false_breakouts(frame)
    previous=frame.close.shift(1);tr=pd.concat([frame.high-frame.low,(frame.high-previous).abs(),(frame.low-previous).abs()],axis=1).max(axis=1)
    atr=tr.ewm(alpha=1/14,adjust=False).mean().iloc[-1]/last.close
    spread=abs(frame.close.ewm(span=20,adjust=False).mean().iloc[-1]-frame.close.ewm(span=50,adjust=False).mean().iloc[-1])/last.close
    expected_regime='volatile' if atr>=.03 else 'trending' if spread>=.005 else 'ranging'
    stale=analyze(rows,'1h','live',as_of_ms=rows[-1]['timestamp']+4*3600000)
    plan=position_size(1000,float(last.close),float(last.close)*.98,.5)
    # A future append cannot retrospectively alter the earlier breakout series.
    cut=len(frame)-10;pu,pd_=false_breakouts(frame.iloc[:cut])
    checks={'regime_rule':result['regime']==expected_regime,'false_break_up':bool(up.iloc[-1])==bool(expected_up),
            'false_break_down':bool(down.iloc[-1])==bool(expected_down),
            'future_prefix':np.array_equal(up.iloc[:cut],pu) and np.array_equal(down.iloc[:cut],pd_),
            'stale_no_trade':stale['decision']=='NO_TRADE','risk_budget':plan['planned_loss_including_assumed_costs']<=5.000000001,
            'uncalibrated_probability_absent':result.get('confidence_probability') is None,
            'no_execution':result['execution_allowed'] is False}
    return {'at_utc':str(frame.index[-1]),'checks':checks,'decision':result['decision'],'regime':result['regime'],
            'false_breakout_labels':{'up':bool(expected_up),'down':bool(expected_down)},'reasons':result['reasons']}


def run_exam(root,output):
    manifest,receipt=verified_manifest(root);cases=[]
    for coin in COINS:
        part=manifest['partitions'][coin+'/2026-08'];rows=[]
        for name,digest in sorted(part['source_sha256'].items()):
            path=Path(root)/'raw'/coin/name
            if sha256(path)!=digest:raise ValueError('Unseen source checksum changed.')
            rows.extend(archive_rows(path,part['start'],part['end']))
        source=pd.DataFrame(rows);source.index=pd.to_datetime(source.pop('timestamp'),unit='ms',utc=True)
        frame,_=derive_validate(source,'1h')
        for end in np.linspace(250,len(frame),10,dtype=int):
            result=evaluate_window(frame.iloc[end-200:end]);result['coin']=coin;cases.append(result)
    counts=Counter('PASS' if passed else 'FAIL' for case in cases for passed in case['checks'].values())
    result={'dataset_manifest_sha256':receipt['manifest_sha256'],'period':'2026-08, chronological final holdout',
            'scenarios':len(cases),'checks':dict(counts),'cases':cases,
            'scope':'Previously unexamined real windows; independent arithmetic labels for documented rules and safety invariants.',
            'not_scored':['Human expertise','Profitability','Participant intent/liquidity narrative','Subjective SL optimality','Unlabelled complex chart patterns'],
            'warning':'Mechanical correctness is not expert-trader equivalence or a calibrated success probability.'}
    atomic_json(Path(output),result);return result
