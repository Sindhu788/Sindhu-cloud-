"""Score independent labelled fixtures; the analyzer never reads answer keys."""
import json
from pathlib import Path

from trading_intelligence.analysis import analyze, Evidence, evaluate_evidence, position_size

FIXTURES=Path(__file__).with_name('fixtures')


def evaluate_case(case):
    if case['kind']=='candles':
        return analyze(case['candles'],case.get('timeframe','1h'),'synthetic')
    if case['kind']=='evidence':
        return evaluate_evidence([Evidence(**e) for e in case['evidence']],
                                 enough_data=case.get('enough_data',True),invalidated=case.get('invalidated',False))
    if case['kind']=='risk':return position_size(**case['input'])
    raise ValueError('Unknown exam task')


def run_exam():
    inputs=json.loads((FIXTURES/'exam_inputs.json').read_text())
    keys=json.loads((FIXTURES/'answer_keys.json').read_text())
    results=[];tp=fp=fn=tn=0
    for case in inputs:
        expected=keys[case['id']]
        try:
            response=evaluate_case(case);second=evaluate_case(case)
            consistent=response==second
            actual=response
            for part in expected.get('path','').split('.'):
                if part:actual=actual[part]
            if expected.get('error'):passed=False
            elif 'contains' in expected:passed=expected['contains'] in actual
            elif 'max' in expected:passed=actual<=expected['max']+1e-9
            else:passed=actual==expected['value']
            if isinstance(expected.get('value'),bool):
                if expected['value'] and actual:tp+=1
                elif expected['value']:fn+=1
                elif actual:fp+=1
                else:tn+=1
            # An explanation must reflect the evaluator's actual decision.
            explanation_ok=response.get('decision')!='NO_TRADE' or bool(response.get('reasons'))
            passed=bool(passed and consistent and explanation_ok)
            result={'id':case['id'],'category':case['category'],'pass':passed,'consistent':consistent,'explanation_ok':explanation_ok}
            if not passed:result.update(expected=expected,actual=actual)
        except ValueError as exc:
            result={'id':case['id'],'category':case['category'],'pass':bool(expected.get('error')),'error':str(exc)}
        results.append(result)
    passed=sum(r['pass'] for r in results)
    categories={}
    for item in results:
        counts=categories.setdefault(item['category'],{'passed':0,'total':0})
        counts['total']+=1;counts['passed']+=int(item['pass'])
    return {'dataset':'Versioned synthetic recognition fixtures v1','passed':passed,'total':len(results),
            'score_pct':passed/len(results)*100,'true_positive':tp,'false_positive':fp,'false_negative':fn,'true_negative':tn,
            'failures':[r for r in results if not r['pass']],'results':results,'categories':categories,
            'coverage':'Recognition, structure, indicators, risk, invalidation, contradictory evidence and input quality',
            'profitability_tested':False,'warning':'A synthetic exam score does not establish live trading performance.'}


if __name__=='__main__':
    result=run_exam();print(json.dumps(result,indent=2));raise SystemExit(bool(result['failures']))
