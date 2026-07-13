from fastapi import APIRouter

from data_engine import storage

router = APIRouter()


@router.get("/api/automation/optimizations")
def list_optimizations(limit: int = 200):
    """Every optimization comparison record the pipeline has produced --
    used by the Backtest History page's original-vs-optimized comparison
    (Part 2.3), keyed to a batch via storage.get_optimization_for_batch()
    in /api/backtest-history itself; this list endpoint exists for direct
    lookup/debugging."""
    return {"optimizations": storage.list_optimizations(limit=limit)}
