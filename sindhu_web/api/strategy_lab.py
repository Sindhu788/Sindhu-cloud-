from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from data_engine import storage
from paper_trading import strategy_lab

router = APIRouter()


@router.get("/api/strategy-lab/latest")
def get_latest_scan():
    """The current honest finding: either the most recent qualifying
    strategy (real win rate, real PnL, real trade count) or an explicit
    'nothing found yet' -- never a losing/weak strategy dressed up as
    best. Runs the very first scan on demand if none has ever run, so a
    brand-new install doesn't show a blank page waiting for the weekly
    scheduler."""
    scan = storage.get_latest_strategy_lab_scan()
    if scan is None:
        scan = strategy_lab.scan_for_profitable_strategy()
    return {
        "scan": scan,
        "min_closed_trades": strategy_lab.MIN_CLOSED_TRADES,
        "min_win_rate": strategy_lab.MIN_WIN_RATE,
        "scan_interval_days": strategy_lab.SCAN_INTERVAL_DAYS,
    }


@router.get("/api/strategy-lab/history")
def get_scan_history(limit: int = 20):
    return {"scans": storage.list_strategy_lab_scans(limit)}


@router.post("/api/strategy-lab/scan-now")
def scan_now():
    """Manual 'Scan Now' -- same real scan the weekly scheduler runs, just
    triggered on demand instead of waiting for the next scheduled tick."""
    return {"scan": strategy_lab.scan_for_profitable_strategy()}


class ApproveRequest(BaseModel):
    scan_id: int
    strategy_id: str


@router.post("/api/strategy-lab/approve")
def approve(body: ApproveRequest):
    """The one-click approval gate -- the ONLY way a Strategy Lab finding
    can start feeding live Paper Trading / Telegram. Never called
    automatically."""
    try:
        scan = strategy_lab.approve_candidate(body.scan_id, body.strategy_id)
    except strategy_lab.ApprovalError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"scan": scan}
