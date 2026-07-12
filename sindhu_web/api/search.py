from fastapi import APIRouter

from data_engine import storage
from backtest_engine import strategy_library as lib
from sindhu_web.api.data import _default_exchange

router = APIRouter()


@router.get("/api/search")
def search(q: str = ""):
    """Global search across the entities a trader actually looks for --
    fans out to the same storage/library functions each page already
    uses, so this is purely composition, not a new data layer."""
    q = q.strip()
    if not q:
        return {"coins": [], "strategies": [], "lessons": [], "reports": [], "trades": []}
    q_lower = q.lower()
    exchange = _default_exchange()

    coins = [s for s in storage.load_symbols(exchange) if q_lower in s.lower()][:10]
    strategies = lib.search(q)[:10]
    lessons = [
        {"id": l["id"], "title": l["title"], "category": l["category"]}
        for l in storage.list_lessons() if q_lower in l["title"].lower() or q_lower in (l.get("description") or "").lower()
    ][:10]
    reports = [
        {"batch_id": b["batch_id"], "strategy_name": b["strategy_name"], "created_at": b["created_at"]}
        for b in storage.list_recent_batches(limit=200) if q_lower in b["strategy_name"].lower()
    ][:10]
    trades = storage.search_trades(q, limit=10)

    return {"coins": coins, "strategies": strategies, "lessons": lessons, "reports": reports, "trades": trades}
