"""Master plan A9/A13: MAIN_WALLET for the dashboard. GET is read-only (summary, open positions, last journal events); POST
/api/wallet/unpause/{strategy_id} is the only write and is the manual un-pause the plan requires (state-changing requests already need
the login session and the X-Sindhu-Token header, see sindhu_web/security.py)."""
from fastapi import APIRouter, HTTPException

from paper_trading import wallet

router = APIRouter()


@router.get("/api/wallet")
def get_wallet(journal_limit: int = 20, closed_limit: int = 0):
    s = wallet.summary()
    s["open"] = wallet.open_positions()
    s["journal"] = wallet.journal(max(1, min(int(journal_limit), 500)))
    s["reconciliation"] = wallet.reconcile()
    # master plan V2 PG3: last mark price per open symbol (live P&L) and, on request, the closed wallet trades (newest first)
    s["marks"] = {p["symbol"]: wallet._marks.get(p["symbol"]) for p in s["open"]}
    if closed_limit:
        s["closed"] = list(reversed(wallet.closed_positions()))[:max(1, min(int(closed_limit), 1000))]
    return s


@router.get("/api/wallet/equity")
def get_wallet_equity():
    """Master plan V2 PG2 (U8): MAIN_WALLET equity curve = start balance, then + each closed trade's realized P&L at its close time,
    then the current equity (cash + open positions at their last mark). Drawdown is computed from the same points by the page."""
    s = wallet.summary()
    pts = [{"t": s.get("created_at"), "equity": wallet.START_BALANCE, "kind": "start"}]
    eq = wallet.START_BALANCE
    for p in wallet.closed_positions():
        eq += float(p.get("pnl") or 0.0)
        pts.append({"t": p.get("closed_at"), "equity": round(eq, 4), "kind": "close", "symbol": p.get("symbol")})
    import time as _t
    pts.append({"t": _t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime()), "equity": s["equity"], "kind": "now"})
    return {"wallet": s["wallet"], "start_balance": wallet.START_BALANCE, "points": [p for p in pts if p["t"]], "paper_only": True}


@router.post("/api/wallet/unpause/{strategy_id}")
def unpause(strategy_id: str):
    if not wallet.unpause(strategy_id):
        raise HTTPException(404, "strategy is not paused for MAIN_WALLET")
    return {"ok": True}
