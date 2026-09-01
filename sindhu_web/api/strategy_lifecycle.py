"""Strategy Lifecycle page (Part 3 of the Strategy Lifecycle task): one
consolidated table -- one row per active strategy -- combining each
strategy's real backtest result (already computed, same source as the
Compare page), Part 1's real computed why-win/why-loss summary, and Part 2's
confirmation-strictness optimizer results (Medium/Strict variants), all read
from the Part 0 checkpoint files rather than recomputed here. Read-only;
this module does not run backtests or build strategies -- it just presents
what Parts 1/2 already produced plus the existing paper-trading activation
endpoint (unchanged, still fully gated by Wilson/Confluence/etc. at signal
time)."""

from fastapi import APIRouter

from backtest_engine import strategy_library, lifecycle_checkpoint as ckpt
from data_engine import storage
from sindhu_web import cache
from sindhu_web.api.home import _compute_strategy_summary

router = APIRouter()

PART1_TASK = "part1_why_win_loss"
PART2_TASK = "part2_optimizer"


def _baseline_row(meta, summary_by_id):
    """Master Task 2, Part 4.2: this page used to run its OWN
    latest_completed_batch_for_strategy_name + get_batch_results pair for
    every single active strategy on every request (measured: 45s cold,
    same class of slowness as the pre-fix Compare page) -- a THIRD
    from-scratch reimplementation of the exact same "aggregate this
    strategy's latest batch" computation as Home and Compare. Reusing the
    one shared, cached summary (summary_by_id, built once per request from
    cache.cached("strategy_aggregate_summary", ...)) removes that cost
    entirely for every strategy the summary already covers. The only
    strategies NOT in that summary are ones with no completed batch yet or
    zero total_trades (the summary skips those on purpose) -- for those,
    fall back to a direct (cheap, since there's nothing to aggregate) check
    so the "not yet backtested" case still reports correctly."""
    row = summary_by_id.get(meta["id"])
    if row:
        return {
            "profit_factor": row["profit_factor"], "net_pnl": row["net_pnl"],
            "win_rate_pct": row["win_rate"], "total_trades": row["trades"],
            "batch_id": row["batch_id"],
        }
    batch_id = storage.latest_completed_batch_for_strategy_name(meta["name"])
    return {"profit_factor": None, "net_pnl": None, "win_rate_pct": None,
            "total_trades": 0, "batch_id": batch_id}


@router.get("/api/strategy-lifecycle")
def get_strategy_lifecycle():
    active = [s for s in strategy_library.list_all() if not s.get("archived")]

    part1 = ckpt.read_only(PART1_TASK) or {"items": {}}
    part2 = ckpt.read_only(PART2_TASK) or {"items": {}}
    summary_by_id = {r["id"]: r for r in cache.cached("strategy_aggregate_summary", 30, _compute_strategy_summary)["strategies"]}
    # Master Task 2, Part 4.2: one query for every strategy's paper config
    # instead of a separate get_paper_strategy_config() round trip per
    # strategy in the loop below (49 individual connections, each paying
    # WAL/busy_timeout setup + lock-wait cost under concurrent engine load).
    paper_configs = storage.list_paper_strategy_configs()

    rows = []
    for meta in active:
        sid = meta["id"]
        baseline = _baseline_row(meta, summary_by_id)

        p1_item = part1["items"].get(sid)
        why_summary = None
        if p1_item and p1_item.get("status") == "done" and isinstance(p1_item.get("result"), dict):
            why_summary = p1_item["result"].get("why_summary")

        optimizer = {"medium": None, "strict": None, "not_applicable_reason": None}
        for level in ("medium", "strict"):
            item = part2["items"].get(f"{sid}:{level}")
            if item and item.get("status") == "done" and isinstance(item.get("result"), dict):
                r = item["result"]
                if "profit_factor" in r:
                    optimizer[level] = {
                        "profit_factor": r.get("profit_factor"),
                        "net_pnl": r.get("net_pnl"),
                        "win_rate_pct": r.get("win_rate_pct"),
                        "additions": r.get("additions"),
                        "variant_strategy_id": r.get("variant_strategy_id"),
                    }
        if optimizer["medium"] is None and optimizer["strict"] is None:
            optimizer["not_applicable_reason"] = (
                "Optimizer not yet run or run in progress for this strategy"
                if f"{sid}:medium" not in part2["items"] and f"{sid}:strict" not in part2["items"]
                else "In progress"
            )

        rows.append({
            "strategy_id": sid,
            "name": meta["name"],
            "backtest": baseline,
            "why_summary": why_summary,
            "optimizer": optimizer,
            "paper_config": paper_configs.get(sid) or {
                "strategy_id": sid, "enabled": False, "priority": 5,
                "supported_coins": [], "supported_market_types": [],
                "risk_pct_override": None, "max_open_trades_override": None,
            },
        })

    return {
        "rows": rows,
        "part1_status": ckpt.summary(part1) if part1["items"] else None,
        "part2_status": ckpt.summary(part2) if part2["items"] else None,
    }
