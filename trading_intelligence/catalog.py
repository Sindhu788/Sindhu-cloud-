"""Read-only adapter around the existing 154-entry versioned strategy library."""
import hashlib
import json
from pathlib import Path
import re

from trading_intelligence import VERSION

ROOT=Path(__file__).resolve().parents[1]
LIBRARY=ROOT/'strategies/library'


def strategy_library(directory=None):
    rows=[]
    for path in sorted(Path(directory or LIBRARY).glob('*/meta.json')):
        try:
            meta=json.loads(path.read_text(encoding='utf-8'))
            version=int(meta['current_version'])
            raw=(path.parent/'versions'/f'v{version}.json').read_bytes()
            config=json.loads(raw)
            concepts=set(config.get('concepts_used') or [])
            indicators={x.get('name') for x in config.get('indicators',[]) if x.get('name')}
            for key in ('entry_conditions','long_entry_conditions','short_entry_conditions','confirmation_conditions','exit_conditions'):
                for cond in config.get(key,[]):
                    if cond.get('name'):concepts.add(cond['name'])
                    if cond.get('indicator'):indicators.add(cond['indicator'])
            rows.append({'id':path.parent.name,'name':meta.get('name',config.get('name')),'version':version,
                         'definition_sha256':hashlib.sha256(raw).hexdigest(),'shared_core_version':VERSION,
                         'concepts':sorted(concepts),'indicators':sorted(indicators),
                         'entry':{k:config.get(k) for k in ('long_entry_conditions','short_entry_conditions','entry_conditions','entry_rule_groups')},
                         'exit':config.get('exit_conditions',[]),'invalidation':config.get('stop_loss'),
                         'take_profit':config.get('take_profit'),'dependencies':config.get('timeframes',{}),
                         'regime_suitability':config.get('trend_filter') or 'NOT TESTED',
                         'status':'rejected' if meta.get('safety_status')=='blocked' else 'experimental',
                         'historical_snapshot':meta.get('backtest_snapshot'),
                         'tested_performance':'NOT TESTED','sample_size':None,
                         'uncertainty':'Definition loaded; validity and profitability require independent tests.',
                         'archived':bool(meta.get('archived',False))})
        except (OSError,ValueError,KeyError,TypeError):
            rows.append({'id':path.parent.name,'status':'rejected','error':'Invalid or missing strategy version'})
    return rows


def load_strategy_config(strategy_id,version=None):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',strategy_id):raise ValueError('Invalid strategy id')
    path=LIBRARY/strategy_id
    if version is None:version=int(json.loads((path/'meta.json').read_text())['current_version'])
    if not isinstance(version,int) or version<1:raise ValueError('Invalid strategy version')
    from backtest_engine.strategy_config import StrategyConfig
    return StrategyConfig.from_dict(json.loads((path/'versions'/f'v{version}.json').read_text(encoding='utf-8')))


def evaluate_existing_strategy(strategy_id,rows,timeframe='1h'):
    """Execute saved rule definitions against explicit input; never open orders."""
    from backtest_engine.configured_strategy import ConfiguredStrategy
    from backtest_engine.validator import validate
    from trading_intelligence.research import validate_candles
    config=load_strategy_config(strategy_id)
    meta=json.loads((LIBRARY/strategy_id/'meta.json').read_text(encoding='utf-8'))
    if meta.get('safety_status')=='blocked' or meta.get('archived'):
        return {'decision':'NO_TRADE','reasons':['Strategy is blocked or archived.'],'execution_allowed':False}
    errors=validate(config)
    if errors:return {'decision':'NO_TRADE','reasons':errors,'execution_allowed':False}
    roles=config.timeframes or {}
    if len(set(roles.values()))>1:
        return {'decision':'NO_TRADE','reasons':['Native higher-timeframe closed candles are required; no synthetic HTF substitution.'],'execution_allowed':False}
    if roles and timeframe not in roles.values():raise ValueError('Candle timeframe does not match strategy')
    frame=validate_candles(rows,timeframe,max_rows=2000)
    if len(frame)<200:return {'decision':'NO_TRADE','reasons':['200 candle warmup required'],'execution_allowed':False}
    strategy=ConfiguredStrategy(config);strategy.prepare(frame)
    signal=strategy.on_bar(frame,len(frame)-1,None)
    return {'strategy_id':strategy_id,'signal':None if signal is None else vars(signal),
            'decision':'NO_TRADE' if signal is None else 'PAPER_CANDIDATE','execution_allowed':False,
            'status':'experimental','warning':'A rule firing is not paper approval or evidence of profitability.'}
