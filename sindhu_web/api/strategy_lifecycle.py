"""Strategy Lifecycle page (Part 3 of the Strategy Lifecycle task): one
consolidated table -- one row per active strategy -- combining each
strategy's real backtest result (already computed, same source as the
Compare page), Part 1's real computed why-win/why-loss summary, and Part 2's
confirmation-strictness optimizer results (Medium/Strict variants), all read
from the Part 0 checkpoint files rather than recomputed here. Read-only;
this module does not run backtests or build strategies -- it just presents
what Parts 1/2 already produced plus the existing paper-trading activation
endpoint (unchanged, still fully gated by Wilson/Confluence/etc. at signal
time).

Grand Master Prompt, Phase 2.1: added `lifecycle_stage` -- a discrete stage
name per strategy (Created -> Paper Trading -> Performance Analysis ->
Promoted/Evolution-Escalated/Needs-Optimization -> Paused/Archived), purely
DERIVED at read time from data that already exists elsewhere (backtest
summary, paper_strategy_config, paper_strategy_performance, drawdown-guard
pauses, bot_strategies lineage). No new state machine or storage was added
-- this can never disagree with the real underlying data because it always
recomputes from it fresh.

Phase 2.5: added `evolution_summary` per row (comparisons/rollback counts
from the existing evolution_comparisons table, grouped once per request
rather than reusing evolution_engine.engine) so the page also shows whether
a strategy's optimization/Evolution history has been trending better or
worse, without a second dashboard.
"""

from collections import defaultdict

from fastapi import APIRouter, HTTPException

from backtest_engine import strategy_library, lifecycle_checkpoint as ckpt
from data_engine import storage
from paper_trading import pattern_stats
from sindhu_web import cache
from sindhu_web.strategy_aggregate import compute_strategy_summary as _compute_strategy_summary

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


def _compute_lifecycle_stage(meta, baseline, paper_cfg, paper_perf, has_evolution_lineage, is_paused):
    """Phase 2.1: purely derived, never stored. `paper_perf` is this
    strategy's row from storage.list_paper_strategy_performance() (real
    closed-trade count/PnL) or None if it has never closed a paper trade."""
    if meta.get("archived"):
        return "Archived"
    if baseline.get("batch_id") is None:
        return "Created -- Not Yet Backtested"
    enabled = bool(paper_cfg and paper_cfg.get("enabled"))
    if not enabled:
        return "Backtested -- Awaiting Paper Trading Activation"
    if is_paused:
        return "Continuous Monitoring -- Paused (Performance Degraded)"
    trades = paper_perf["trades"] if paper_perf else 0
    if trades < pattern_stats.MIN_SAMPLE_SIZE:
        return f"Paper Trading -- Accumulating Trades ({trades}/{pattern_stats.MIN_SAMPLE_SIZE})"
    pnl = paper_perf["total_pnl"] if paper_perf else 0.0
    if pnl is not None and pnl >= 0:
        return "Performance Analysis -- Passing (Live-Candidate)"
    if has_evolution_lineage:
        return "Evolution Escalated -- Generating Variants"
    return "Performance Analysis -- Needs Optimization"


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
    # Phase 2.1/2.5: same "one query for every strategy" batching pattern,
    # extended to the three extra data sources the new stage/evolution
    # fields need -- never one query per strategy in the loop below.
    paper_perf_by_id = {r["strategy_id"]: r for r in storage.list_paper_strategy_performance()}
    paused_ids = {p["strategy_id"] for p in storage.list_paused_strategies()}
    lineage_base_ids = {b["base_id"] for b in storage.list_bot_strategies(limit=5000) if b.get("base_id")}
    # Phase 2.4: the last background-computed Auto-Downgrade state (see
    # paper_trading/auto_downgrade.py's hourly scheduler) -- reading the
    # already-stored table here, never recomputing per strategy on every
    # page load (that would mean up to 75 fresh last-100-trades queries).
    downgrade_states = storage.list_paper_downgrade_states()
    comparisons_by_base = defaultdict(list)
    # Fix, 2026-09-12: same incident class as compute_strategy_summary's
    # backtest_batches fix -- this page is the one place evolution_summary
    # data is read from a route also mounted on the lightweight cloud
    # runner (see this module's own docstring), but evolution_comparisons
    # is excluded from the cloud runner's curated Postgres schema (see
    # data_engine/db_backend.py's POSTGRES_SCHEMA docstring), so this threw
    # UndefinedTable uncaught on every single cloud request. Every other
    # caller of list_evolution_comparisons (Evolution/Risk Department/
    # Report Builder) is local-machine-only, where the table always
    # exists, so the safe fallback belongs here at this one cloud-reachable
    # call site, not inside storage.list_evolution_comparisons itself.
    try:
        evolution_comparisons = storage.list_evolution_comparisons(limit=5000)
    except Exception:
        evolution_comparisons = []
    for c in evolution_comparisons:
        if c.get("base_id"):
            comparisons_by_base[c["base_id"]].append(c)

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

        paper_cfg = paper_configs.get(sid) or {
            "strategy_id": sid, "enabled": False, "priority": 5,
            "supported_coins": [], "supported_market_types": [],
            "risk_pct_override": None, "max_open_trades_override": None,
        }
        comparisons = comparisons_by_base.get(sid, [])

        rows.append({
            "strategy_id": sid,
            "name": meta["name"],
            "backtest": baseline,
            "why_summary": why_summary,
            "optimizer": optimizer,
            "paper_config": paper_cfg,
            "lifecycle_stage": _compute_lifecycle_stage(
                meta, baseline, paper_cfg, paper_perf_by_id.get(sid),
                sid in lineage_base_ids, sid in paused_ids,
            ),
            "evolution_summary": {
                "comparisons_count": len(comparisons),
                "rollback_count": sum(1 for c in comparisons if c.get("rolled_back")),
                "has_lineage": sid in lineage_base_ids,
            },
            "live_downgrade": downgrade_states.get(sid),
        })

    return {
        "rows": rows,
        "part1_status": ckpt.summary(part1) if part1["items"] else None,
        "part2_status": ckpt.summary(part2) if part2["items"] else None,
    }


def compute_failure_reasons(strategy_id):
    """Phase 2.3: for a losing strategy, a real, computed breakdown of
    where its backtest losses/wins concentrate -- by coin and by exit
    reason (both stored per-trade in backtest_trades). Market-condition
    (trending/ranging) is NOT available for backtest trade data -- it is
    only recorded for live paper-trading pattern memory -- so this is
    reported honestly as unavailable rather than fabricated.
    """
    try:
        meta = strategy_library.get_meta(strategy_id)
    except FileNotFoundError:
        return None
    if not meta:
        return None
    batch_id = storage.latest_completed_batch_for_strategy_name(meta["name"])
    if not batch_id:
        return {"available": False, "reason": "No completed backtest yet for this strategy."}
    trades = storage.get_trades(batch_id)
    if not trades:
        return {"available": False, "reason": "Latest backtest batch has no trade records."}

    by_coin = defaultdict(lambda: {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0})
    by_exit_reason = defaultdict(lambda: {"trades": 0, "pnl": 0.0})
    net_pnl, win_count, loss_count = 0.0, 0, 0
    for t in trades:
        pnl = t["pnl"] or 0.0
        net_pnl += pnl
        coin = by_coin[t["symbol"]]
        coin["trades"] += 1
        coin["pnl"] += pnl
        if pnl > 0:
            coin["wins"] += 1
            win_count += 1
        elif pnl < 0:
            coin["losses"] += 1
            loss_count += 1
        reason = by_exit_reason[t["exit_reason"] or "unknown"]
        reason["trades"] += 1
        reason["pnl"] += pnl

    coin_rows = [{"symbol": k, **{kk: (round(vv, 2) if kk == "pnl" else vv) for kk, vv in v.items()}}
                 for k, v in by_coin.items()]
    coin_rows.sort(key=lambda r: r["pnl"])
    reason_rows = [{"exit_reason": k, **{kk: (round(vv, 2) if kk == "pnl" else vv) for kk, vv in v.items()}}
                   for k, v in by_exit_reason.items()]
    reason_rows.sort(key=lambda r: r["pnl"])

    return {
        "available": True,
        "batch_id": batch_id,
        "total_trades": len(trades),
        "net_pnl": round(net_pnl, 2),
        "win_count": win_count,
        "loss_count": loss_count,
        "by_coin": coin_rows,
        "by_exit_reason": reason_rows,
        "market_regime_breakdown_available": False,
        "note": ("Market-condition (trending/ranging) breakdown is not available for backtest "
                 "trade data -- only symbol and exit-reason are recorded per trade."),
    }


@router.get("/api/strategy-lifecycle/{strategy_id}/failure-reasons")
def get_failure_reasons(strategy_id: str):
    result = compute_failure_reasons(strategy_id)
    if result is None:
        raise HTTPException(404, "Strategy not found")
    return result
