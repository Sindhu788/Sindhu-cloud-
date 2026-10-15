"""Bounded educational endpoints, protected by each app's existing middleware."""
from pathlib import Path
import json
import re
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Literal

from trading_intelligence import VERSION

router=APIRouter()


@router.get('/api/intelligence/historical-lab')
def historical_lab(limit: int=50):
    from data_engine.paths import DATA_DIR
    root=Path(DATA_DIR)/'research_lab';progress_path=root/'progress.json'
    if not progress_path.exists():return {'status':'UNAVAILABLE','rows':[],'automatic_approval':False}
    progress=json.loads(progress_path.read_text());run_id=progress.get('run_id','')
    if not re.fullmatch(r'[0-9a-f]{20}',run_id):raise HTTPException(503,'Research checkpoint invalid.')
    results=[]
    for path in (root/run_id).glob('*-*.json'):
        if path.stat().st_size>200000:continue
        results.append(json.loads(path.read_text()))
    def rank(row):
        val=row.get('results',{}).get('validation',{})
        eligible=(not row.get('policy_quarantined',True) and row.get('leakage_audit',{}).get('pass') is True
                  and val.get('sample_size',0)>=30)
        return (eligible,(val.get('expectancy_r_week_block95') or [-1e9])[0] if eligible else -1e9)
    results.sort(key=rank,reverse=True)
    return {'status':progress.get('stage'),'run_id':run_id,'completed_cases':len(results),'rows':results[:max(1,min(limit,100))],
            'ranking':'Policy and validation evidence only; holdout never selects this order.','automatic_approval':False,
            'execution':'Spot long/flat. Short definitions and OI/funding/book claims are not validated by spot OHLCV.'}


class AnalysisRequest(BaseModel):
    candles: list[dict]=Field(min_length=1,max_length=2000)
    timeframe: str='1h'
    data_label: Literal['synthetic','historical','live']='synthetic'
    as_of_ms: int | None=None


def checked(function,*args,**kwargs):
    try:return function(*args,**kwargs)
    except (ValueError,KeyError,TypeError) as exc:
        # Validation messages contain field descriptions, never submitted payloads.
        raise HTTPException(422,str(exc)) from None


@router.get('/how-to-trade')
def page():
    return FileResponse(Path(__file__).resolve().parents[1]/'static/how_to_trade.html')


@router.get('/api/intelligence/health')
def health():return {'status':'ok','version':VERSION,'educational_only':True,'network_execution':False}


@router.get('/api/intelligence/shared-wallet')
def shared_wallet():
    # Never create an ephemeral cloud wallet or fall back to legacy books.
    from data_engine import db_backend
    from data_engine.paths import DATA_DIR
    if db_backend.IS_POSTGRES:
        try:
            wallet,ident=_postgres_shared_wallet()
            result=wallet.snapshot(ident)
            from trading_intelligence.cloud_shared_scanner import status
            result['scanner']=status()
            return result
        except Exception:
            raise HTTPException(503,'Verified PostgreSQL shared wallet unavailable; migration/activation requires approval.') from None
    from trading_intelligence.shared_wallet import SharedWallet
    root=Path(DATA_DIR)/'shared_paper'
    try:
        receipt=json.loads((root/'owner_session.json').read_text(encoding='utf-8'))
        from trading_intelligence.shared_postgres import local_wallet
        wallet=local_wallet(root)
        result=wallet.snapshot(receipt['session_id'])
        if result['archive_sha256']!=receipt['archive_sha256']:
            raise ValueError('Archive identity differs')
        scanner_path=root/'scanner_state.json'
        scanner=json.loads(scanner_path.read_text()) if scanner_path.exists() else {}
        import psutil
        running=False
        try:
            process=psutil.Process(scanner.get('pid',0))
            running=any('run_shared_paper.py' in part for part in process.cmdline()) and scanner.get('state') in ('STARTING','RUNNING','WAITING_FOR_FRESH_DATA')
        except (psutil.Error,ValueError):pass
        result['scanner']={'running':running,'state':scanner.get('state','NOT_STARTED'),
                           'last_successful_scan_utc':scanner.get('last_successful_scan_utc'),
                           'evaluated_symbols':scanner.get('evaluated_symbols',[]),
                           'evaluated_timeframes':scanner.get('evaluated_timeframes',[]),
                           'cycles_completed':scanner.get('cycles_completed',0),
                           'selected_versions':scanner.get('selected_versions',{}),
                           'strategy_ids':scanner.get('strategy_ids',[]),
                           'standalone_lessons':'NOT EXECUTABLE: explicit entry/exit/risk provenance required',
                           'public_delivery':False,'real_orders':0}
        return result
    except Exception:
        raise HTTPException(503,'Verified local shared wallet is unavailable; legacy balances are excluded.') from None


@router.post('/api/intelligence/shared-wallet/{operation}')
def shared_wallet_control(operation:str):
    if operation not in ('pause','resume'):raise HTTPException(404,'Unknown shared wallet control')
    current=shared_wallet()
    from data_engine.paths import DATA_DIR
    from trading_intelligence.shared_wallet import SharedWallet
    import uuid
    from data_engine import db_backend
    from trading_intelligence.shared_postgres import local_wallet
    wallet=_postgres_shared_wallet()[0] if db_backend.IS_POSTGRES else local_wallet(Path(DATA_DIR)/'shared_paper')
    wallet.event(current['session_id'],'control-'+uuid.uuid4().hex,'control',{'paused':operation=='pause'})
    return shared_wallet()


def _postgres_shared_wallet():
    from trading_intelligence.shared_postgres import configured_wallet
    wallet=configured_wallet()
    from trading_intelligence.shared_selection import active_session
    return wallet,active_session(wallet,postgres=True)


@router.get('/api/intelligence/database-health')
def database_health():
    from data_engine import storage,db_backend
    try:
        with storage.get_conn() as conn:
            ok=conn.execute('SELECT 1').fetchone()[0]==1
        return {'status':'ok' if ok else 'failed','database_connected':ok,
                'backend':'postgresql' if db_backend.IS_POSTGRES else 'sqlite'}
    except Exception:raise HTTPException(503,'Database connectivity check failed') from None


@router.post('/api/intelligence/virtual-sessions')
def virtual_session_create():
    from data_engine import storage
    from trading_intelligence.sessions import create_session
    with storage.get_conn() as conn:return create_session(conn)


@router.get('/api/intelligence/virtual-sessions/{session_id}')
def virtual_session_get(session_id:str):
    from data_engine import storage
    from trading_intelligence.sessions import load_session,session_paused
    with storage.get_conn() as conn:
        return {**checked(load_session,conn,session_id).snapshot(),'paused':session_paused(conn,session_id)}


@router.post('/api/intelligence/virtual-sessions/{session_id}/pause')
def virtual_session_pause(session_id:str):
    from data_engine import storage
    from trading_intelligence.sessions import control_session
    with storage.get_conn() as conn:return checked(control_session,conn,session_id,True)


@router.post('/api/intelligence/virtual-sessions/{session_id}/resume')
def virtual_session_resume(session_id:str):
    from data_engine import storage
    from trading_intelligence.sessions import control_session
    with storage.get_conn() as conn:return checked(control_session,conn,session_id,False)


@router.post('/api/intelligence/virtual-sessions/{session_id}/example')
def virtual_session_example(session_id:str):
    from data_engine import storage
    from trading_intelligence.sessions import run_example
    with storage.get_conn() as conn:return checked(run_example,conn,session_id)


@router.get('/api/intelligence/curriculum')
def curriculum():
    from trading_intelligence.curriculum import curriculum as load
    return load()


@router.get('/api/intelligence/strategies')
def strategies():
    from trading_intelligence.catalog import strategy_library
    return {'version':VERSION,'strategies':strategy_library()}


@router.post('/api/intelligence/analyze')
def analyze(request:AnalysisRequest):
    from trading_intelligence.analysis import analyze as run
    from trading_intelligence.virtual import dry_run_message
    result=checked(run,request.candles,request.timeframe,request.data_label,request.as_of_ms)
    result['telegram_preview']=dry_run_message(result)
    return result


@router.post('/api/intelligence/strategy/{strategy_id}/evaluate')
def strategy_evaluate(strategy_id:str,request:AnalysisRequest):
    from trading_intelligence.catalog import evaluate_existing_strategy
    try:return checked(evaluate_existing_strategy,strategy_id,request.candles,request.timeframe)
    except FileNotFoundError:raise HTTPException(404,'Strategy version not found') from None


@router.post('/api/intelligence/exam')
def exam():
    from trading_intelligence.exam import run_exam
    return run_exam()


@router.get('/api/intelligence/leaderboard')
def leaderboard():
    from trading_intelligence.leaderboard import leaderboard as load
    try:return load()
    except Exception:
        raise HTTPException(503,'Paper history is unavailable; no performance values were inferred') from None


@router.post('/api/intelligence/research/validate')
def research_validate(request:AnalysisRequest):
    from trading_intelligence.research import validate_candles,dataset_hash,chronological_split,walk_forward
    checked(validate_candles,request.candles,request.timeframe)
    return {'rows':len(request.candles),'dataset_sha256':dataset_hash(request.candles),
            'splits':checked(chronological_split,len(request.candles)),
            'walk_forward':walk_forward(len(request.candles)), 'data_label':request.data_label,
            'historical_backtest_completed':False}


@router.post('/api/intelligence/research/baseline')
def baseline(request:AnalysisRequest):
    from trading_intelligence.research import baseline_backtest
    return checked(baseline_backtest,request.candles,request.timeframe,data_label=request.data_label)


@router.post('/api/intelligence/research/evaluate')
def research_evaluate(request:AnalysisRequest):
    from trading_intelligence.research import research_validation,walk_forward_evaluation
    return {'chronological':checked(research_validation,request.candles,request.timeframe,data_label=request.data_label),
            'walk_forward':checked(walk_forward_evaluation,request.candles,request.timeframe,data_label=request.data_label)}
