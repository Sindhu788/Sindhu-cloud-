"""No labels are passed into detectors; separate frozen ground truth scores."""
import json,math
from pathlib import Path
from backtest_engine import concepts as c
from trading_intelligence.analysis import detect
from trading_intelligence.practical import structure_events,false_breakouts
from trading_intelligence.research import validate_candles

def evaluate(case):
    df=validate_candles(case['candles']);kind=case['detector']
    if kind=='detect':
        value=detect(df)[case['path']]
        return case['contains'] in value if case.get('contains') else value
    if kind=='levels':return float(c.support_resistance(df)[0 if case['path']=='support' else 1].iloc[-1])
    if kind=='order_block':return float(c.order_blocks(df)[0].iloc[-1])
    if kind=='structure_event':return bool(structure_events(df)[0].iloc[-1])
    if kind in ('false_up','false_down'):return bool(false_breakouts(df)[kind=='false_down'].iloc[-1])
    raise ValueError('Unknown practical detector')

def run_exam():
    root=Path(__file__).with_name('fixtures')
    inputs=json.loads((root/'practical_inputs.json').read_text());keys=json.loads((root/'practical_keys.json').read_text())
    failed=[];tp=tn=fp=fn=0
    for case in inputs:
        expected=keys[case['id']]
        try:
            actual=evaluate(case)
            passed=actual==expected if isinstance(expected,bool) else math.isclose(actual,expected,abs_tol=1e-8)
            if isinstance(expected,bool):
                if expected and actual:tp+=1
                elif expected:fn+=1
                elif actual:fp+=1
                else:tn+=1
            if not passed:failed.append({'id':case['id'],'expected':expected,'actual':actual})
        except Exception as exc:failed.append({'id':case['id'],'error':type(exc).__name__+': '+str(exc)[:150]})
    return {'tests':len(inputs),'passed':len(inputs)-len(failed),'failed':failed,'true_positive':tp,'true_negative':tn,'false_positive':fp,'false_negative':fn,
            'scope':'New versioned synthetic geometry; not independent live or profitability evidence',
            'insufficient_labelled_coverage':['head_shoulders','triangles','flags','pennants','wedges','channels'],
            'unsupported_feeds':['open_interest','funding','order_book']}
