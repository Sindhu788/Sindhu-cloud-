"""Master plan A9/A13: MAIN_WALLET for the dashboard. GET is read-only (summary, open positions, last journal events); POST
/api/wallet/unpause/{strategy_id} is the only write and is the manual un-pause the plan requires (state-changing requests already need
the login session and the X-Sindhu-Token header, see sindhu_web/security.py)."""
from fastapi import APIRouter, HTTPException

from paper_trading import wallet

router = APIRouter()


@router.get("/api/wallet")
def get_wallet(journal_limit: int = 20):
    s = wallet.summary()
    s["open"] = wallet.open_positions()
    s["journal"] = wallet.journal(max(1, min(int(journal_limit), 200)))
    s["reconciliation"] = wallet.reconcile()
    return s


@router.post("/api/wallet/unpause/{strategy_id}")
def unpause(strategy_id: str):
    if not wallet.unpause(strategy_id):
        raise HTTPException(404, "strategy is not paused for MAIN_WALLET")
    return {"ok": True}
