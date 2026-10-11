"""One real-data scanner cycle in a fresh local educational sandbox."""
import json
import os
from pathlib import Path
import platform
import sys
import urllib.request
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ.update(DATABASE_URL='',SINDHU_DATA_DIR=str(ROOT/'data/isolated_live_scan'),
                  SINDHU_SAFE_START='0',SINDHU_TELEGRAM_DRY_RUN='1',SINDHU_PUBLIC_SIGNAL_OWNER='disabled',
                  SINDHU_CLOUD_MODE='0',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
if os.name=='nt':platform._wmi_query=lambda *a,**k: (_ for _ in ()).throw(OSError('WMI unavailable'))


def main():
    import pandas as pd
    from data_engine import storage
    from paper_trading import config,market_state,signal_generator,strategy_matcher,lesson_matcher
    from paper_trading.engine import PaperTradingEngine
    from trading_intelligence.catalog import strategy_library,load_strategy_config
    storage.init_db();config.update(dry_run=True,engine_enabled=False)
    frames={};source=None;errors=[]
    for host in ('https://data-api.binance.vision','https://api.binance.com'):
        try:
            for tf in ('15m','1h'):
                request=urllib.request.Request(host+'/api/v3/klines?symbol=BTCUSDT&interval='+tf+'&limit=300',headers={'User-Agent':'SINDHU-educational-QA'})
                with urllib.request.urlopen(request,timeout=20) as response:rows=json.load(response)
                values=[[int(r[0]),*map(float,r[1:6])] for r in rows]
                frame=pd.DataFrame(values,columns=['timestamp','open','high','low','close','volume'])
                frame.index=pd.to_datetime(frame.pop('timestamp'),unit='ms',utc=True);frames[tf]=frame
            source=host;break
        except Exception as exc:errors.append(type(exc).__name__)
    if source is None:
        print(json.dumps({'status':'BLOCKED','reason':'Public live market data unavailable','error_types':errors}),flush=True);return 2
    item=next(x for x in strategy_library() if x.get('dependencies')=={'entry':'1h'} and not x.get('archived') and x.get('status')!='rejected')
    candidates=[{'strategy_id':item['id'],'strategy_name':item['name'],'strategy_version':item['version'],'priority':5,'config':load_strategy_config(item['id'])}]
    def get_frame(*args,**kwargs):return frames[kwargs['interval']].copy()
    from backtest_engine.mtf_context import MultiTimeframeContext
    def context(exchange,symbol,roles,*args,**kwargs):return MultiTimeframeContext.from_frames({role:frames[tf].copy() for role,tf in roles.items()},roles)
    # Substitute public read-only data transport and explicit test selection;
    # real classification, validation, candidates, gates and receipt code run.
    engine=PaperTradingEngine()
    with patch.object(market_state,'get_ohlcv',get_frame),patch.object(signal_generator,'MultiTimeframeContext',context),\
         patch.object(strategy_matcher,'relevant_strategies',return_value=candidates),\
         patch.object(lesson_matcher,'relevant_lessons',return_value=[]):
        result=engine.run_single_coin_scan_now('BTCUSDT')
    with storage.get_conn() as conn:
        row=conn.execute('SELECT outcome,coins_scanned,candidates,accepted,rejected,no_trade,errors,market_json FROM paper_scan_log ORDER BY completed_at DESC LIMIT 1').fetchone()
        opened=conn.execute("SELECT count(*) FROM paper_positions WHERE status='open'").fetchone()[0]
    receipt=dict(zip(('outcome','coins_scanned','candidates','accepted','rejected','no_trade','errors','market_json'),row))
    receipt['market_data']=json.loads(receipt.pop('market_json'))
    passed=receipt['outcome']=='complete' and receipt['coins_scanned']==1 and receipt['errors']==0 and opened==0 and bool(receipt['market_data'])
    print(json.dumps({'status':'PASS' if passed else 'FAIL','data_label':'live','source':source,'scanner_result':result,
                      'receipt':receipt,'open_positions':opened,'real_orders':0,'public_telegram_sends':0,
                      'scope':'Single actual core cycle, public transport substituted; not production scheduler or 24/7 proof.'}),flush=True)
    return 0 if passed else 1

if __name__=='__main__':raise SystemExit(main())
