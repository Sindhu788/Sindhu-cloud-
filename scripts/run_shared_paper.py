"""Bounded local scanner, existing approval gates, one educational cash wallet.

The data transport is Binance's public spot API. No exchange order endpoint,
Telegram client, AI inference or production configuration is used here.
"""
import argparse
from contextlib import ExitStack
import json
from itertools import count
import os
from pathlib import Path
import platform
import sys
import time
import urllib.request
import urllib.error
import uuid
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
DATA_ROOT=ROOT/'data/recovery_main'
qa_root=os.environ.get('SINDHU_PAPER_QA_DATA_DIR')
if qa_root:
    DATA_ROOT=Path(qa_root).resolve()
    if not DATA_ROOT.is_relative_to((ROOT/'data/functional_qa').resolve()) or (DATA_ROOT/'shared_paper/backend.json').exists():
        raise ValueError('Paper QA requires isolated local SQLite storage; PostgreSQL marker refused')
os.environ.update(DATABASE_URL='',SINDHU_DATA_DIR=str(DATA_ROOT),SINDHU_SAFE_START='0',
                  SINDHU_TELEGRAM_DRY_RUN='1',SINDHU_PUBLIC_SIGNAL_OWNER='disabled',SINDHU_CLOUD_MODE='0',
                  OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
if os.name=='nt':platform._wmi_query=lambda *a,**k: (_ for _ in ()).throw(OSError('WMI unavailable'))


def public_json(path):
    url='https://data-api.binance.vision/api/v3/'+path
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'SINDHU-educational-paper'}),timeout=20) as response:
        return json.load(response)


def quote(symbol):
    result=public_json('ticker/price?symbol='+symbol)
    return result['price'],int(time.time()*1000)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--cycles',type=int,default=1)
    args=parser.parse_args()
    import pandas as pd
    from data_engine import storage,feature_toggles
    from paper_trading import config,market_state,signal_generator,strategy_matcher,lesson_matcher,kill_switch
    from paper_trading.engine import PaperTradingEngine
    from paper_trading.market_data_guard import closed_recent_frame, MarketDataRejected
    from backtest_engine.validator import validate
    from backtest_engine.mtf_context import MultiTimeframeContext
    from trading_intelligence.catalog import strategy_library,load_strategy_config
    from trading_intelligence.shared_wallet import now
    from trading_intelligence.shared_postgres import local_wallet
    from trading_intelligence.shared_execution import SharedExecution
    root=DATA_ROOT/'shared_paper'
    # OS file lock, released on process exit. No stale-PID delete or duplicate worker.
    lock=open(root/'scanner.lock','a+b')
    if os.name=='nt':
        import msvcrt
        lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0)
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:raise RuntimeError('Existing shared scanner owns the worker lock') from None
    session=json.loads((root/'owner_session.json').read_text())['session_id']
    wallet=local_wallet(root)
    storage.init_db()
    # Existing user settings, with stronger caps for this isolated account.
    configured=root/'worker_configuration_receipt.json'
    if not configured.exists():
        original=json.loads(Path('D:/sindhu/data/config/paper_trading_settings.json').read_text())
        config.update(**dict(original,engine_enabled=False,dry_run=False,initial_balance=100,
                             risk_pct_default=min(float(original.get('risk_pct_default',1)),1)))
        configured.write_text(json.dumps({'at_utc':now(),'initial_balance':100,'scope':'isolated local settings'}),encoding='utf-8')
    settings=config.load()
    if settings.get('initial_balance')!=100 or settings.get('engine_enabled'):
        raise RuntimeError('Shared mode requires $100 and legacy engine_enabled=false; settings were not overwritten')
    from trading_intelligence.paper_eligibility import select_eligible
    manifest_path=root/'eligibility.json'
    if not manifest_path.exists():
        raise RuntimeError('Frozen session allowlist missing; owner approval required before activation')
    selected=select_eligible(json.loads(manifest_path.read_text()),isolated=bool(qa_root))
    engine=PaperTradingEngine();adapter=SharedExecution(wallet,session,engine,quote)
    engine._shared_execution=adapter
    # No narrative curriculum module is treated as a complete entry system.
    # Existing lesson path needs explicit per-concept risk/exit provenance;
    # it remains excluded until that provenance is available.
    receipt={'pid':os.getpid(),'started_at_utc':now(),'session_id':session,'strategy_ids':[x['strategy_id'] for x in selected],
             'concepts':'Compiled concepts within selected strategies; standalone narrative lessons NOT EXECUTABLE',
             'public_delivery':False,'real_orders':0,'state':'STARTING',
             'evaluated_timeframes':['15m','1h'],'storage_scope':'isolated_local_qa' if qa_root else 'approved_shared',
             'selected_versions':{x['strategy_id']:x['strategy_version'] for x in selected}}
    def save():
        temp=root/'scanner_state.tmp';temp.write_text(json.dumps(receipt,indent=2),encoding='utf-8');temp.replace(root/'scanner_state.json')
    save()
    original_log=engine._log_decision
    for cycle in range(args.cycles) if args.cycles else count():
        key=uuid.uuid4().hex;frames={};counter=[0];receipts=[]
        try:
            if kill_switch.is_active() or feature_toggles.is_master_paused():
                raise RuntimeError('Kill switch or master pause active')
            for symbol in ('BTCUSDT','ETHUSDT'):
                for tf in ('15m','1h'):
                    raw=public_json('klines?symbol='+symbol+'&interval='+tf+'&limit=300')
                    df=pd.DataFrame([[int(r[0]),*map(float,r[1:6])] for r in raw],columns=['timestamp','open','high','low','close','volume'])
                    df.index=pd.to_datetime(df.pop('timestamp'),unit='ms',utc=True)
                    frames[(symbol,tf)],r=closed_recent_frame(df,tf);receipts.append(dict(symbol=symbol,**r))
                adapter.monitor(symbol,frames[(symbol,'15m')],next(r for r in receipts if r['symbol']==symbol and r['timeframe']=='15m'))
            def frame(exchange,symbol,interval,**kwargs):return frames[(symbol,interval)].copy()
            def context(exchange,symbol,roles,*args,**kwargs):
                return MultiTimeframeContext.from_frames({role:frames[(symbol,tf)].copy() for role,tf in roles.items()},roles)
            def log(exchange,symbol,candidate,decision,reason,snapshot,**kwargs):
                counter[0]+=1
                if decision in ('rejected','no_trade'):
                    wallet.event(session,key+'-decision-'+str(counter[0]),'rejection' if decision=='rejected' else 'no_trade',
                                 {'symbol':symbol,'strategy_id':candidate.get('strategy_id'),'reason':reason})
                return original_log(exchange,symbol,candidate,decision,reason,snapshot,**kwargs)
            generate=signal_generator.generate_candidates
            def candidates(*args,**kwargs):
                result=generate(*args,**kwargs)
                for i,c in enumerate(result):
                    wallet.event(session,key+'-candidate-'+args[1]+'-'+str(i),'candidate',{'symbol':args[1],'strategy_id':c.get('strategy_id')})
                return result
            with ExitStack() as stack:
                for obj,name,value in [(market_state,'get_ohlcv',frame),(signal_generator,'MultiTimeframeContext',context),
                                       (strategy_matcher,'relevant_strategies',lambda *a:selected),
                                       (lesson_matcher,'relevant_lessons',lambda *a:[]),
                                       (signal_generator,'generate_candidates',candidates),(engine,'_log_decision',log)]:
                    stack.enter_context(patch.object(obj,name,value))
                results=[engine.run_single_coin_scan_now(symbol) for symbol in ('BTCUSDT','ETHUSDT')]
            success=all(not r.get('error') and not r.get('skipped') for r in results)
            wallet.event(session,key,'scan',{'success':success,'symbols':['BTCUSDT','ETHUSDT'],'candle_receipts':receipts})
            receipt.update(state='RUNNING' if success else 'ERROR',last_completed_utc=now(),last_successful_scan_utc=now() if success else receipt.get('last_successful_scan_utc'),
                           evaluated_symbols=['BTCUSDT','ETHUSDT'],results=results,cycles_completed=cycle+1)
            if success:
                receipt.pop('error_type',None);receipt.pop('error_reason',None)
            save();print(json.dumps({'scanner':receipt['state'],'completed_utc':receipt['last_completed_utc'],'cycle':cycle+1,'results':results}),flush=True)
        except (MarketDataRejected, urllib.error.URLError, TimeoutError) as exc:
            # Invalid/stale data blocks this cycle, not the whole service.
            # A later cycle must pass the original guard again before entries.
            reason=str(exc) if isinstance(exc,MarketDataRejected) else type(exc).__name__
            wallet.event(session,key+'-feed','no_trade',{'reason':reason,'feed_health':'BLOCKED'})
            wallet.event(session,key,'scan',{'success':False,'symbols':['BTCUSDT','ETHUSDT']})
            receipt.update(state='WAITING_FOR_FRESH_DATA',error_type=type(exc).__name__,
                           error_reason=reason,last_completed_utc=now(),cycles_completed=cycle+1)
            save();print(json.dumps({'scanner':receipt['state'],'reason':reason}),flush=True)
        except Exception as exc:
            receipt.update(state='ERROR',error_type=type(exc).__name__,last_completed_utc=now());save()
            print(json.dumps({'scanner':'ERROR','error_type':type(exc).__name__}),flush=True)
            return 1
        if args.cycles and cycle+1>=args.cycles:break
        time.sleep(60)
    receipt['state']='COMPLETED_BOUNDED_TEST';save()
    return 0


if __name__=='__main__':raise SystemExit(main())
