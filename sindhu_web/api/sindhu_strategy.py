from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from data_engine import storage
from sindhu_strategy import generator, lifecycle

router = APIRouter()


@router.get("/api/sindhu-strategy/today")
def today_candidates():
    return {"candidates": generator.today_candidates()}


@router.get("/api/sindhu-strategy/daily-log")
def daily_log(date: str = None):
    date = date or datetime.now(timezone.utc).isoformat()[:10]
    return storage.get_daily_generation(date)


@router.get("/api/sindhu-strategy/candidates")
def list_candidates(made_with_ai: Optional[bool] = None, limit: int = 500):
    """Every SINDHU-generated candidate ever created (both origins),
    generation 1 only -- these are the daily candidates themselves;
    evolution_engine.mutator branches later generations off of whichever
    ones get promoted into that lineage, listed separately via
    /api/evolution/strategies."""
    rows = [s for s in storage.list_bot_strategies(status="active", limit=limit) if s["generation"] == 1
            and s["origin"] in ("sindhu_ai", "sindhu_deterministic")]
    if made_with_ai is not None:
        rows = [s for s in rows if s["made_with_ai"] == made_with_ai]
    return {"candidates": rows}


@router.get("/api/sindhu-strategy/candidates/{candidate_id}")
def candidate_detail(candidate_id: str):
    row = storage.get_bot_strategy(candidate_id)
    if not row:
        raise HTTPException(404, "candidate not found")
    return row


@router.post("/api/sindhu-strategy/generate")
def generate_now():
    """Manually triggers today's generation cycle -- a safe no-op if
    today's 11 already exist (see generator.generate_daily_candidates),
    so this can be called freely without risking exceeding the daily cap."""
    created = generator.generate_daily_candidates()
    return {"created": created, "count": len(created)}


class BacktestRequest(BaseModel):
    exchange: str = "binance"
    symbols: List[str]
    initial_balance: float = 10000.0
    risk_pct_default: float = 1.0


@router.post("/api/sindhu-strategy/candidates/{candidate_id}/backtest")
def backtest_candidate(candidate_id: str, req: BacktestRequest):
    """B.4 -- routes this candidate through the exact same validate() ->
    run_mtf_batch() -> generate_report() pipeline used for user-imported
    strategies, then stores its Evolution Score."""
    try:
        result = lifecycle.validate_and_backtest(
            candidate_id, req.exchange, req.symbols,
            settings={"initial_balance": req.initial_balance, "risk_pct_default": req.risk_pct_default},
        )
    except ValueError:
        raise HTTPException(404, "candidate not found")
    return result
