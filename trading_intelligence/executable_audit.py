"""Run every saved definition through the real rule interpreter, offline."""
from collections import Counter
import json,math
import pandas as pd
from trading_intelligence.catalog import strategy_library,load_strategy_config

def native_frame(timeframe,n=240):
    frequencies={'1m':'min','3m':'3min','5m':'5min','15m':'15min','30m':'30min','1h':'h','2h':'2h','4h':'4h','6h':'6h','8h':'8h','12h':'12h','1d':'D','3d':'3D','1w':'W-MON','1M':'MS'}
    if timeframe not in frequencies:raise ValueError('Unsupported native timeframe: '+timeframe)
    index=pd.date_range(end='2026-10-01',periods=n,freq=frequencies[timeframe],tz='UTC')
    close=[100+math.sin(i/6)*4+i*.01 for i in range(n)]
    return pd.DataFrame({'open':[v-.1 for v in close],'high':[v+1 for v in close],
                         'low':[v-1 for v in close],'close':close,'volume':[100+i%11 for i in range(n)]},index=index)

def audit():
    from backtest_engine.configured_strategy import ConfiguredStrategy
    from backtest_engine.mtf_context import MultiTimeframeContext
    from backtest_engine.validator import validate
    results=[]
    for item in strategy_library():
        row={'strategy_id':item['id'],'version':item.get('version'),'performance':'NOT TESTED'}
        try:
            config=load_strategy_config(item['id']);errors=validate(config)
            if errors:row.update(status='INVALID_DEFINITION',errors=errors)
            else:
                roles=config.timeframes or {'entry':'1h'}
                frames={role:native_frame(tf) for role,tf in roles.items()}
                context=MultiTimeframeContext.from_frames(frames,roles)
                strategy=ConfiguredStrategy(config);frame=strategy.prepare_context(context);frame=strategy.prepare(frame)
                for i in range(max(0,len(frame)-10),len(frame)):strategy.on_bar(frame,i,None)
                row.update(status='SMOKE_PASS',native_roles=roles,policy_blocked=item.get('archived') or item.get('status')=='rejected')
        except Exception as exc:row.update(status='EXECUTION_ERROR',error=type(exc).__name__+': '+str(exc)[:240])
        results.append(row)
    return {'definitions':len(results),'counts':dict(Counter(r['status'] for r in results)),
            'scope':'Offline prepare + 10 on_bar calls per valid definition; synthetic native roles, no fills or profitability claims',
            'results':results}

if __name__=='__main__':
    result=audit();print(json.dumps(result),flush=True)
