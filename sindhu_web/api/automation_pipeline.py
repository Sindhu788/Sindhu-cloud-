from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from data_engine import storage
from backtest_engine import strategy_library as lib
from automation_pipeline.pipeline import trigger_pipeline_for_strategy

router = APIRouter()


@router.get("/api/automation/optimizations")
def list_optimizations(limit: int = 200):
    """Every optimization comparison record the pipeline has produced --
    used by the Backtest History page's original-vs-optimized comparison
    (Part 2.3), keyed to a batch via storage.get_optimization_for_batch()
    in /api/backtest-history itself; this list endpoint exists for direct
    lookup/debugging."""
    return {"optimizations": storage.list_optimizations(limit=limit)}


class TriggerPipelineRequest(BaseModel):
    strategy_id: str
    symbols: Optional[List[str]] = None


@router.post("/api/automation/trigger")
def trigger_pipeline(req: TriggerPipelineRequest):
    """Manually starts the automation pipeline for an already-saved,
    already-ready strategy. Not used by the normal import flow (that
    auto-triggers on its own, always against every downloaded coin) --
    this exists so the full backtest -> optimize -> re-backtest -> compare
    -> paper-trading chain can be exercised quickly against a handful of
    coins (via `symbols`) for verification, instead of waiting on the full
    coin universe."""
    try:
        cfg = lib.load(req.strategy_id)
    except FileNotFoundError:
        raise HTTPException(404, "strategy not found")
    job_id = trigger_pipeline_for_strategy(req.strategy_id, cfg.name, symbols=req.symbols)
    if job_id is None:
        raise HTTPException(409, "Could not start -- another pipeline or backtest is already running.")
    return {"job_id": job_id}
