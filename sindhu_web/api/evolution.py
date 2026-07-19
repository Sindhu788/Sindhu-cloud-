from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from data_engine import storage
from evolution_engine.engine import engine
from evolution_engine import champion, generation_manager, mutator

router = APIRouter()


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


@router.get("/api/evolution/status")
def evolution_status():
    """Evolution Engine running state, current job/checkpoint, and the
    Governor's live resource/queue/experiment-budget numbers -- everything
    the Evolution Dashboard's top summary needs in one call."""
    return engine.status()


@router.post("/api/evolution/start")
def start_evolution():
    started = engine.start()
    if not started:
        raise HTTPException(409, "Evolution Engine is already running.")
    return {"started": True}


@router.post("/api/evolution/stop")
def stop_evolution():
    engine.stop()
    return {"stopped": True}


@router.post("/api/evolution/run-tick")
def run_tick_now():
    """Manually runs one Analyze->Mutate->Archive->Rank pass immediately,
    without waiting for the next scheduled tick or needing the background
    loop running at all -- lets the CEO (or a test) see an immediate
    result on demand."""
    if not engine.job_id:
        engine.job_id = f"evo_manual_{int(datetime.now().timestamp() * 1000)}"
        storage.create_evolution_job(engine.job_id, _now_iso())
    engine._tick()
    return engine.status()


@router.get("/api/evolution/strategies")
def list_strategies(base_id: str = None, status: str = "active", limit: int = 500):
    return {"strategies": storage.list_bot_strategies(base_id=base_id, status=status, limit=limit)}


@router.get("/api/evolution/strategies/{base_id}/lineage")
def strategy_lineage(base_id: str):
    history = mutator.compare_generations(base_id)
    if not history:
        raise HTTPException(404, "no BOT strategy lineage with that base_id")
    return {"base_id": base_id, "generations": history}


@router.get("/api/evolution/ranking")
def strategy_ranking(base_id: str = None):
    return {"ranking": mutator.rank_strategies(base_id=base_id)}


@router.get("/api/evolution/research/dna-correlations")
def dna_correlations(min_sample: int = 3):
    return {"correlations": mutator.research_dna_correlations(min_sample=min_sample)}


@router.get("/api/evolution/lessons")
def list_lessons(base_id: str = None, status: str = "active", limit: int = 500):
    return {"lessons": storage.list_bot_lessons(base_id=base_id, status=status, limit=limit)}


@router.get("/api/evolution/champions")
def current_champions():
    return {"champions": champion.current_champions()}


@router.get("/api/evolution/knowledge-versions")
def knowledge_versions(limit: int = 50):
    return {"versions": storage.list_knowledge_versions(limit=limit)}
