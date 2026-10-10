"""Bounded educational endpoints, protected by each app's existing middleware."""
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Literal

from trading_intelligence import VERSION

router=APIRouter()


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
